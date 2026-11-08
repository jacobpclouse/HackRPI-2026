"""Shared analyze pipeline for uploads and samples."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from darkwatch.detection import classifier
from darkwatch.imagery import ais_compare, chips, geotiff, ground_truth, proposals

MAX_QUICKLOOK = 2048
FOOTNOTE = "Detections are radar returns scored by a model. An unmatched vessel is not evidence of wrongdoing."


def _ms(t0: float) -> int:
    return int(round((time.perf_counter() - t0) * 1000))


def _id(i: int) -> str:
    return f"U{i:03d}"


def _histogram(scores: list[float], threshold: float, bins: int = 20) -> dict:
    counts, edges = np.histogram(scores, bins=bins, range=(0.0, 1.0))
    return {
        "bins": bins,
        "counts": [int(x) for x in counts],
        "edges": [round(float(x), 4) for x in edges],
        "threshold": threshold,
    }


def _draw_boxes(img: Image.Image, detections: list[dict], gt: dict | None) -> Image.Image:
    out = img.convert("RGB")
    draw = ImageDraw.Draw(out)
    for det in detections:
        status = det["status"]
        if status == "edge":
            continue
        x0, y0, x1, y1 = det["bbox"]
        ais = (det.get("ais") or {}).get("status")
        if ais == "matched":
            color = (61, 214, 140)
            width = 2
        elif ais == "dark_candidate":
            color = (255, 77, 79)
            width = 2
        elif status == "vessel_like":
            color = (230, 234, 240)
            width = 2
        else:
            color = (84, 94, 108)
            width = 1
        draw.rectangle([x0, y0, x1, y1], outline=color, width=width)
        draw.text((x0 + 2, max(0, y0 - 10)), det["id"], fill=color)
    if gt and gt.get("boxes"):
        for box in gt["boxes"]:
            x0, y0, x1, y1 = box["bbox"]
            draw.rectangle([x0, y0, x1, y1], outline=(255, 77, 79), width=2)
    return out


def _save_png(arr: np.ndarray | Image.Image) -> bytes:
    if isinstance(arr, np.ndarray):
        img = Image.fromarray(arr)
        if img.mode != "L":
            img = img.convert("L")
    else:
        img = arr
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _quicklook(img8: np.ndarray) -> tuple[np.ndarray, float]:
    h, w = img8.shape[:2]
    scale = 1.0
    long_side = max(h, w)
    if long_side > MAX_QUICKLOOK:
        scale = MAX_QUICKLOOK / long_side
        img = Image.fromarray(img8).resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
        return np.array(img), scale
    return img8, 1.0


def analyze(
    file_bytes: bytes,
    filename: str,
    xml_bytes: bytes | None = None,
    user_time: str | None = None,
    kind: str | None = None,
) -> dict:
    timings = {}
    t_all = time.perf_counter()
    t0 = time.perf_counter()
    suffix = (filename or "").lower()
    is_tiff = (kind == "geotiff") or suffix.endswith((".tif", ".tiff"))
    geo = None
    img8: np.ndarray
    spacing_m = 10.0
    spacing_label = "assumed"
    bbox = None
    acquisition = None
    if is_tiff:
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".tif", delete=False)
        try:
            tmp.write(file_bytes)
            tmp.close()
            geo = geotiff.load(Path(tmp.name), filename=filename, user_time=user_time)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
        img8 = geo.array
        spacing_m = geo.spacing_m
        spacing_label = geo.spacing_note
        bbox = geo.bbox
        acquisition = geo.acquisition
        if user_time and (acquisition is None or acquisition.get("source") != "geotiff_tag"):
            if acquisition is None or acquisition.get("source") in ("filename", "user", "tiff_datetime"):
                if acquisition is None or acquisition.get("source") == "user" or (
                    acquisition.get("source") != "geotiff_tag" and user_time and acquisition.get("source") != "tiff_datetime"
                ):
                    pass
        if acquisition is None and user_time:
            acquisition = geotiff.parse_acquisition({}, filename, user_time)
        kind = "geotiff"
    else:
        Image.MAX_IMAGE_PIXELS = 80_000_000
        pil = Image.open(io.BytesIO(file_bytes)).convert("L")
        img8 = np.array(pil)
        if user_time:
            acquisition = geotiff.parse_acquisition({}, filename, user_time)
        kind = "jpeg" if suffix.endswith((".jpg", ".jpeg")) else "png"
    height, width = img8.shape[:2]
    timings["ingest"] = _ms(t0)

    t0 = time.perf_counter()
    # JPG/PNG already 8-bit; GeoTIFF was remapped in geotiff.load.
    timings["normalize"] = _ms(t0)

    t0 = time.perf_counter()
    props = proposals.proposals(img8)
    timings["propose"] = _ms(t0)
    n_propose = len(props)

    t0 = time.perf_counter()
    extracted = chips.extract(img8, props, valid=None if geo is None else geo.valid)
    scored: list[tuple] = []
    threshold = classifier.threshold() if classifier.available() else 0.5
    batch = []
    batch_idx = []
    for i, (chip, edge) in enumerate(extracted):
        if edge:
            scored.append((None, True, chip))
            continue
        batch.append(chip)
        batch_idx.append(i)
        scored.append((None, False, chip))
    if batch:
        if not classifier.available():
            raise RuntimeError("Classifier is unavailable (ONNX missing).")
        probs = classifier.score(np.stack(batch))
        for j, p in zip(batch_idx, probs, strict=True):
            chip = scored[j][2]
            scored[j] = (float(p), False, chip)
    timings["classify"] = _ms(t0)

    detections = []
    scores_for_hist = []
    n_vessel = n_rej = n_edge = 0
    for i, (prop, (score, edge, chip)) in enumerate(zip(props, scored, strict=True), start=1):
        if edge:
            status = "edge"
            n_edge += 1
        elif score is not None and score >= threshold:
            status = "vessel_like"
            n_vessel += 1
        else:
            status = "rejected"
            n_rej += 1
        if score is not None:
            scores_for_hist.append(score)
        side_px = max(prop.row_max - prop.row_min + 1, prop.col_max - prop.col_min + 1)
        length_m = side_px * spacing_m
        det = {
            "id": _id(i),
            "bbox": [prop.col_min, prop.row_min, prop.col_max, prop.row_max],
            "centroid": {"row": prop.row, "col": prop.col},
            "pixels": prop.pixels,
            "peak": round(float(prop.peak), 2),
            "score": None if score is None else round(float(score), 4),
            "status": status,
            "length_m": round(float(length_m), 1),
            "length_note": "approximate" if kind == "geotiff" else "assumed",
            "lat": None,
            "lon": None,
            "ais": None,
            "chip": chip,
        }
        if geo is not None:
            ll = geotiff.pixel_to_lonlat(geo, prop.row, prop.col)
            if ll:
                det["lon"], det["lat"] = ll
        detections.append(det)

    t0 = time.perf_counter()
    gt = None
    if xml_bytes:
        boxes = ground_truth.parse_voc(xml_bytes)
        scored_dets = [d for d in detections if d["status"] == "vessel_like"]
        gt = ground_truth.score(scored_dets, boxes)
        # boxes on all detections for drawing; GT scoring used vessel-like only
        lookup = {d["id"]: d.get("gt_hit") for d in scored_dets}
        for d in detections:
            d["gt_hit"] = lookup.get(d["id"])
    timings["ground_truth"] = _ms(t0)

    t0 = time.perf_counter()
    ais = None
    if kind == "geotiff":
        if not bbox or not acquisition or not acquisition.get("time"):
            ais = {"available": False, "reason": "No AIS data for this area and time in the loaded store"}
            if not bbox:
                ais["reason"] = "This file has no location data, so AIS comparison isn't available"
            elif not acquisition:
                ais["reason"] = "No acquisition time, so AIS comparison isn't available"
        else:
            ais = ais_compare.compare(detections, bbox, acquisition["time"])
        if ais and not ais.get("available"):
            for d in detections:
                if d["status"] == "vessel_like":
                    d["ais"] = {"status": "no_ais", "name": None, "mmsi": None, "match_km": None}
    timings["ais"] = _ms(t0)

    t0 = time.perf_counter()
    look, scale = _quicklook(img8)
    look_img = Image.fromarray(look)
    annotated = _draw_boxes(Image.fromarray(img8), detections, gt)
    chip_pngs = {d["id"]: _save_png(d.pop("chip")) for d in detections}
    quicklook_png = _save_png(look_img)
    annotated_png = _save_png(annotated)
    timings["render"] = _ms(t0)
    timings["total"] = _ms(t_all)

    area_km2 = None
    if kind == "geotiff":
        area_km2 = round((width * spacing_m * height * spacing_m) / 1e6, 2)

    if kind == "geotiff" and ais and not ais.get("available"):
        mode_note = "Location found. No AIS data for this area and time, so AIS comparison is unavailable."
        if ais.get("reason", "").startswith("This file"):
            mode_note = ais["reason"]
    elif kind != "geotiff":
        mode_note = "No location or time in this file. Showing detection only. Pixel spacing assumed 10 m."
    else:
        mode_note = None

    mean_conf = None
    vessel_scores = [d["score"] for d in detections if d["status"] == "vessel_like" and d["score"] is not None]
    if vessel_scores:
        mean_conf = round(float(np.mean(vessel_scores)), 3)

    funnel = {
        "ingest": {"count": 1, "ms": timings["ingest"]},
        "normalize": {"count": 1, "ms": timings["normalize"]},
        "propose": {"count": n_propose, "ms": timings["propose"]},
        "classify": {"keep": n_vessel, "reject": n_rej, "edge": n_edge, "ms": timings["classify"]},
        "ais": None
        if not ais or not ais.get("available")
        else {
            "matched": ais.get("matched", 0),
            "dark": ais.get("dark_candidates", 0),
            "only": len(ais.get("ais_only") or []),
            "ms": timings["ais"],
        },
    }

    return {
        "filename": filename,
        "kind": kind,
        "mode_note": mode_note,
        "width": width,
        "height": height,
        "spacing_m": spacing_m,
        "spacing_label": spacing_label,
        "area_km2": area_km2,
        "bbox": bbox,
        "acquisition": acquisition,
        "threshold": threshold,
        "timings_ms": timings,
        "funnel": funnel,
        "detections": detections,
        "ground_truth": gt,
        "ais": ais,
        "histogram": _histogram(scores_for_hist, threshold) if scores_for_hist else None,
        "heroes": {
            "ships_found": n_vessel,
            "rejected": n_rej,
            "mean_confidence": mean_conf,
            "processed_s": round(timings["total"] / 1000, 2),
        },
        "quicklook_scale": scale,
        "footnote": FOOTNOTE,
        "_files": {
            "quicklook": quicklook_png,
            "annotated": annotated_png,
            "chips": chip_pngs,
        },
    }
