"""Analyze-imagery routes: upload, samples, artifacts."""

from __future__ import annotations

import json
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image

from nimbus import paths
from nimbus.imagery.pipeline import analyze

router = APIRouter()

MAX_BYTES = 60 * 1024 * 1024
LRU_SIZE = 10
JPEG = b"\xff\xd8\xff"
PNG = b"\x89PNG"
TIFF_LE = b"II*\x00"
TIFF_BE = b"MM\x00*"

_store: OrderedDict[str, dict] = OrderedDict()

Image.MAX_IMAGE_PIXELS = 80_000_000

SAMPLE_META = {
    "lsssdd": "LS-SSDD test scene {n}, never seen in training",
    "geotiff": "Kattegat, Sentinel-1D, 2 Nov 2026, 10 m",
}


def _kind_from_magic(data: bytes, filename: str) -> str:
    head = data[:16]
    if head.startswith(JPEG):
        return "jpeg"
    if head.startswith(PNG):
        return "png"
    if head.startswith(TIFF_LE) or head.startswith(TIFF_BE):
        return "geotiff"
    raise HTTPException(400, "Unrecognized image. Use JPEG, PNG, or GeoTIFF.")


def _cache_dir(analysis_id: str) -> Path:
    path = paths.imagery_cache_dir() / analysis_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _put(result: dict) -> str:
    analysis_id = uuid.uuid4().hex[:12]
    files = result.pop("_files")
    result["id"] = analysis_id
    folder = _cache_dir(analysis_id)
    (folder / "quicklook.png").write_bytes(files["quicklook"])
    (folder / "annotated.png").write_bytes(files["annotated"])
    chips_dir = folder / "chips"
    chips_dir.mkdir(exist_ok=True)
    for det_id, png in files["chips"].items():
        (chips_dir / f"{det_id}.png").write_bytes(png)
    public = {k: v for k, v in result.items() if not k.startswith("_")}
    (folder / "report.json").write_text(json.dumps(public, default=str))
    _store[analysis_id] = public
    while len(_store) > LRU_SIZE:
        _store.popitem(last=False)
    return analysis_id


def _get(analysis_id: str) -> dict:
    if analysis_id in _store:
        _store.move_to_end(analysis_id)
        return _store[analysis_id]
    path = _cache_dir(analysis_id) / "report.json"
    if path.is_file():
        data = json.loads(path.read_text())
        _store[analysis_id] = data
        return data
    raise HTTPException(404, "Unknown analysis")


def _public(result: dict) -> dict:
    for det in result.get("detections") or []:
        det["chip_url"] = f"/api/imagery/{result['id']}/chips/{det['id']}.png"
    result["quicklook_url"] = f"/api/imagery/{result['id']}/quicklook.png"
    result["annotated_url"] = f"/api/imagery/{result['id']}/annotated.png"
    result["report_url"] = f"/api/imagery/{result['id']}/report.json"
    return result


async def run_analyze(image: bytes, filename: str, xml: bytes | None, acquired_at: str | None, kind: str | None = None):
    if len(image) > MAX_BYTES:
        raise HTTPException(413, "File is over 60 MB. Compress it or crop the scene.")
    if not image:
        raise HTTPException(400, "Empty file.")
    sniffed = _kind_from_magic(image, filename)
    kind = kind or sniffed
    try:
        result = await _to_thread(analyze, image, filename, xml, acquired_at, kind)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    analysis_id = _put(result)
    return _public(_get(analysis_id))


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)


@router.post("/api/imagery/analyze")
async def imagery_analyze(
    image: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    labels: UploadFile | None = File(None),
    acquired_at: str | None = Form(None),
):
    upload = image or file
    if upload is None:
        raise HTTPException(400, "Missing image.")
    data = await upload.read()
    xml = await labels.read() if labels is not None else None
    return await run_analyze(data, upload.filename or "upload", xml, acquired_at)


@router.get("/api/imagery/samples")
def imagery_samples():
    root = paths.samples_dir()
    items = []
    lsssdd = root / "lsssdd"
    if lsssdd.is_dir():
        for jpg in sorted(lsssdd.glob("*.jpg")):
            scene = jpg.stem.split("_")[0]
            xml = jpg.with_suffix(".xml")
            items.append(
                {
                    "name": jpg.name,
                    "title": jpg.stem,
                    "type": "jpeg",
                    "folder": "lsssdd",
                    "has_labels": xml.is_file(),
                    "description": SAMPLE_META["lsssdd"].format(n=scene),
                }
            )
    geotiff_dir = root / "geotiff"
    if geotiff_dir.is_dir():
        for tif in sorted(list(geotiff_dir.glob("*.tif")) + list(geotiff_dir.glob("*.tiff"))):
            items.append(
                {
                    "name": tif.name,
                    "title": tif.stem,
                    "type": "geotiff",
                    "folder": "geotiff",
                    "has_labels": False,
                    "description": SAMPLE_META["geotiff"],
                }
            )
    return {"samples": items}


def _sample_path(name: str) -> Path:
    root = paths.samples_dir()
    for folder in ("lsssdd", "geotiff"):
        candidate = root / folder / name
        if candidate.is_file() and candidate.resolve().is_relative_to(root.resolve()):
            return candidate
    raise HTTPException(404, "Unknown sample")


@router.post("/api/imagery/samples/{name}/analyze")
async def imagery_sample_analyze(name: str):
    path = _sample_path(name)
    xml_path = path.with_suffix(".xml")
    xml = xml_path.read_bytes() if xml_path.is_file() else None
    kind = "geotiff" if path.suffix.lower() in {".tif", ".tiff"} else "jpeg"
    return await run_analyze(path.read_bytes(), path.name, xml, None, kind)


@router.get("/api/imagery/{analysis_id}")
def imagery_get(analysis_id: str):
    return _public(dict(_get(analysis_id)))


@router.get("/api/imagery/{analysis_id}/quicklook.png")
def imagery_quicklook(analysis_id: str):
    _get(analysis_id)
    path = _cache_dir(analysis_id) / "quicklook.png"
    if not path.is_file():
        raise HTTPException(404, "Quicklook missing")
    return Response(path.read_bytes(), media_type="image/png")


@router.get("/api/imagery/{analysis_id}/annotated.png")
def imagery_annotated(analysis_id: str):
    _get(analysis_id)
    path = _cache_dir(analysis_id) / "annotated.png"
    if not path.is_file():
        raise HTTPException(404, "Annotated image missing")
    return Response(path.read_bytes(), media_type="image/png")


@router.get("/api/imagery/{analysis_id}/chips/{det_id}.png")
def imagery_chip(analysis_id: str, det_id: str):
    _get(analysis_id)
    path = _cache_dir(analysis_id) / "chips" / f"{det_id}.png"
    if not path.is_file():
        raise HTTPException(404, "Chip missing")
    return Response(path.read_bytes(), media_type="image/png")


@router.get("/api/imagery/{analysis_id}/report.json")
def imagery_report(analysis_id: str):
    return _get(analysis_id)
