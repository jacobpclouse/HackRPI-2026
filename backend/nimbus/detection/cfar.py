"""Cell-averaging CFAR for SAR intensity, plus a seam for an xView3 model.

The shipped detector is classic CA-CFAR on intensity (exponential clutter,
single-look multiplier). It does not need a GPU. Set XVIEW3_WEIGHTS and
XVIEW3_REPO to select the plug-in seam instead; that path is intentionally
unwired so the demo never downloads weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy import ndimage

from nimbus import config


@dataclass
class Detection:
    row: float
    col: float
    pixels: int
    peak: float
    background: float
    peak_db: float

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "col": self.col,
            "pixels": self.pixels,
            "peak": self.peak,
            "background": self.background,
            "peak_db": round(self.peak_db, 2),
        }


def ca_cfar_mask(
    image: np.ndarray,
    guard: int = 3,
    train: int = 12,
    pfa: float = 1e-7,
    valid: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (detection mask, local background mean).

    Alpha is the standard CA-CFAR factor for exponential clutter:
    N * (Pfa^(-1/N) - 1).
    """
    img = np.asarray(image, dtype=np.float64)
    img = np.where(np.isfinite(img), img, 0.0)
    img = np.clip(img, 0, None)
    outer = 2 * (guard + train) + 1
    inner = 2 * guard + 1
    n_train = outer * outer - inner * inner
    if n_train <= 0:
        raise ValueError("train window must be larger than the guard window")
    sum_outer = ndimage.uniform_filter(img, size=outer, mode="nearest") * (outer * outer)
    sum_inner = ndimage.uniform_filter(img, size=inner, mode="nearest") * (inner * inner)
    background = (sum_outer - sum_inner) / n_train
    alpha = n_train * (pfa ** (-1.0 / n_train) - 1.0)
    detect = (img > alpha * background) & (background > 0)
    border = guard + train
    if border:
        detect[:border, :] = False
        detect[-border:, :] = False
        detect[:, :border] = False
        detect[:, -border:] = False
    if valid is not None:
        detect &= valid.astype(bool)
    return detect, background


def cluster_detections(
    image: np.ndarray,
    mask: np.ndarray,
    background: np.ndarray,
    min_pixels: int = 3,
    max_pixels: int = 150,
    min_peak_db: float = 6.0,
) -> list[Detection]:
    labeled, count = ndimage.label(mask)
    out: list[Detection] = []
    img = np.asarray(image, dtype=np.float64)
    for idx in range(1, int(count) + 1):
        ys, xs = np.where(labeled == idx)
        n = int(ys.size)
        if n < min_pixels or n > max_pixels:
            continue
        weights = np.clip(img[ys, xs], 0, None)
        if not np.any(weights > 0):
            continue
        row = float(np.average(ys, weights=weights))
        col = float(np.average(xs, weights=weights))
        peak = float(weights.max())
        bg = float(np.median(background[ys, xs]))
        if bg <= 0 or peak <= 0:
            continue
        peak_db = 10.0 * np.log10(peak) - 10.0 * np.log10(bg)
        if peak_db < min_peak_db:
            continue
        out.append(
            Detection(
                row=row,
                col=col,
                pixels=n,
                peak=peak,
                background=bg,
                peak_db=float(peak_db),
            )
        )
    out.sort(key=lambda d: d.peak_db, reverse=True)
    return out


class Detector(Protocol):
    """Anything that turns a SAR intensity chip into detections.

    CA-CFAR and a learned model (xView3, a future classifier) are
    interchangeable behind this. ``valid`` is False on land and nodata.
    """

    def detect(self, image: np.ndarray, valid: np.ndarray | None = None) -> list[Detection]: ...


class CFARDetector:
    """Default ship detector. Land should already be False in `valid`."""

    def __init__(
        self,
        guard: int = 3,
        train: int = 12,
        pfa: float = 1e-7,
        min_pixels: int = 3,
        max_pixels: int = 150,
        min_peak_db: float = 6.5,
    ):
        self.guard = guard
        self.train = train
        self.pfa = pfa
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.min_peak_db = min_peak_db

    def detect(self, image: np.ndarray, valid: np.ndarray | None = None) -> list[Detection]:
        mask, background = ca_cfar_mask(
            image, guard=self.guard, train=self.train, pfa=self.pfa, valid=valid
        )
        return cluster_detections(
            image,
            mask,
            background,
            min_pixels=self.min_pixels,
            max_pixels=self.max_pixels,
            min_peak_db=self.min_peak_db,
        )


def make_detector() -> Detector:
    weights = config.xview3_weights()
    repo = config.xview3_repo()
    if weights and repo:
        from nimbus.detection.xview3_adapter import XView3Detector

        return XView3Detector(weights, repo)
    return CFARDetector()

