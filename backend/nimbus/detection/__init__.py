"""Ship detection (CA-CFAR), AIS matching, coverage reports, and chip scoring."""

from nimbus.detection import classifier
from nimbus.detection.analysis import coverage_report, floor_now, sentinel_validation
from nimbus.detection.cfar import (
    CFARDetector,
    Detection,
    Detector,
    ca_cfar_mask,
    cluster_detections,
    make_detector,
)
from nimbus.detection.classifier import ShipClassifier
from nimbus.detection.matching import Fix, Interp, confidence_score, interpolate_track, match_detections
from nimbus.detection.xview3_adapter import XView3Detector

__all__ = [
    "CFARDetector",
    "Detection",
    "Detector",
    "Fix",
    "Interp",
    "ShipClassifier",
    "XView3Detector",
    "ca_cfar_mask",
    "classifier",
    "cluster_detections",
    "confidence_score",
    "coverage_report",
    "floor_now",
    "interpolate_track",
    "make_detector",
    "match_detections",
    "sentinel_validation",
]
