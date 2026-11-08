"""Pascal VOC scoring. A detection is a TP if its centroid falls in a GT box + 4 px."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

PAD_PX = 4


@dataclass
class GtBox:
    name: str
    xmin: int
    ymin: int
    xmax: int
    ymax: int
    hit: bool = False


def parse_voc(xml_bytes: bytes) -> list[GtBox]:
    root = ET.fromstring(xml_bytes)
    boxes = []
    for obj in root.findall("object"):
        box = obj.find("bndbox")
        if box is None:
            continue
        name = (obj.findtext("name") or "ship").strip()
        boxes.append(
            GtBox(
                name=name,
                xmin=int(float(box.findtext("xmin") or 0)),
                ymin=int(float(box.findtext("ymin") or 0)),
                xmax=int(float(box.findtext("xmax") or 0)),
                ymax=int(float(box.findtext("ymax") or 0)),
            )
        )
    return boxes


def score(detections: list[dict], boxes: list[GtBox]) -> dict:
    """detections need centroid col/row. Each GT box is matched at most once."""
    for box in boxes:
        box.hit = False
    tp = 0
    for det in detections:
        col = det["centroid"]["col"]
        row = det["centroid"]["row"]
        for box in boxes:
            if box.hit:
                continue
            if box.xmin - PAD_PX <= col <= box.xmax + PAD_PX and box.ymin - PAD_PX <= row <= box.ymax + PAD_PX:
                box.hit = True
                det["gt_hit"] = True
                tp += 1
                break
        else:
            det["gt_hit"] = False
    fn = sum(1 for box in boxes if not box.hit)
    fp = sum(1 for det in detections if not det.get("gt_hit"))
    n_gt = len(boxes)
    n_det = len(detections)
    precision = (tp / n_det) if n_det else 0.0
    recall = (tp / n_gt) if n_gt else 0.0
    missed = [
        {"name": box.name, "bbox": [box.xmin, box.ymin, box.xmax, box.ymax]}
        for box in boxes
        if not box.hit
    ]
    return {
        "available": True,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "n_gt": n_gt,
        "missed": missed,
        "boxes": [
            {"name": box.name, "bbox": [box.xmin, box.ymin, box.xmax, box.ymax], "hit": box.hit}
            for box in boxes
        ],
    }
