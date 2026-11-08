"""Ship detection (CA-CFAR), AIS matching, coverage reports, and chip scoring."""

from darkwatch.detection import classifier
from darkwatch.detection.analysis import coverage_report, floor_now, sentinel_validation
from darkwatch.detection.cfar import (
    CFARDetector,
    Detection,
    Detector,
    ca_cfar_mask,
    cluster_detections,
    make_detector,
)
from darkwatch.detection.classifier import ShipClassifier
from darkwatch.detection.matching import Fix, Interp, confidence_score, interpolate_track, match_detections
from darkwatch.detection.xview3_adapter import XView3Detector

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
