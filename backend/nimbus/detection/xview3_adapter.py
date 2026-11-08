"""Seam for the DIU xView3 first-place model.

https://github.com/DIUx-xView/xView3_first_place

Nimbus does not ship weights and does not require a GPU. Implement
``xview3_adapter.run(image, valid, weights, repo)`` in that checkout, or
leave this unused. ``make_detector()`` stays on CFAR unless both
XVIEW3_WEIGHTS and XVIEW3_REPO are set.
"""

from __future__ import annotations

import numpy as np

from nimbus.detection.cfar import Detection


class XView3Detector:
    """Runs ``xview3_adapter.run`` from the XVIEW3_REPO checkout."""

    def __init__(self, weights: str, repo: str):
        self.weights = weights
        self.repo = repo

    def detect(self, image: np.ndarray, valid: np.ndarray | None = None) -> list[Detection]:
        import importlib
        import sys

        if self.repo and self.repo not in sys.path:
            sys.path.insert(0, self.repo)
        try:
            adapter = importlib.import_module("xview3_adapter")
        except ImportError as exc:
            raise RuntimeError(
                "XVIEW3_REPO must provide xview3_adapter.run(image, valid, weights). "
                "CFAR remains the detector used by the demo."
            ) from exc
        return adapter.run(image, valid, self.weights, self.repo)
