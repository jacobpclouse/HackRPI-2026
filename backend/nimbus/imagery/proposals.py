"""Bright-spot proposer. Same CA-CFAR-style mask as the training notebook."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage as ndi

from nimbus.imagery import preprocess

MAX_PROPOSALS = 2000


@dataclass
class Proposal:
    row: int
    col: int
    pixels: int
    peak: float
    row_min: int
    col_min: int
    row_max: int
    col_max: int


def proposals(img: np.ndarray, k=None, guard=None, train=None, min_px=None) -> list[Proposal]:
    """Port of the notebook ``proposals()`` mask; extra fields are measurements only.

    Parameters default to ``preprocess.json`` and match the notebook (k=3, guard=5,
    train=15, min_px=3). Do not retune them.
    """
    params = preprocess.proposal_params()
    k = params["k"] if k is None else k
    guard = int(params["guard"] if guard is None else guard)
    train = int(params["train"] if train is None else train)
    min_px = int(params["min_px"] if min_px is None else min_px)

    img = np.asarray(img, dtype=np.float32)
    big = ndi.uniform_filter(img, 2 * train + 1) * (2 * train + 1) ** 2
    small = ndi.uniform_filter(img, 2 * guard + 1) * (2 * guard + 1) ** 2
    bg = (big - small) / ((2 * train + 1) ** 2 - (2 * guard + 1) ** 2)
    mask = img > k * np.maximum(bg, 1.0)
    lab, n = ndi.label(mask)
    if n == 0:
        return []
    idx = list(range(1, n + 1))
    sizes = np.atleast_1d(np.asarray(ndi.sum(mask, lab, idx)))
    keep = [i for i, size in enumerate(sizes) if size >= min_px]
    if not keep:
        return []
    labels = [i + 1 for i in keep]
    peaks = np.atleast_1d(np.asarray(ndi.maximum(img, lab, labels)))
    cents = np.atleast_2d(np.asarray(ndi.center_of_mass(mask, lab, labels), dtype=np.float64))
    slices = ndi.find_objects(lab)
    out: list[Proposal] = []
    for j, i in enumerate(keep):
        r, c = float(cents[j, 0]), float(cents[j, 1])
        sl = slices[i]
        out.append(
            Proposal(
                row=int(r),
                col=int(c),
                pixels=int(sizes[i]),
                peak=float(peaks[j]),
                row_min=int(sl[0].start),
                col_min=int(sl[1].start),
                row_max=int(sl[0].stop - 1),
                col_max=int(sl[1].stop - 1),
            )
        )
    out.sort(key=lambda p: (p.peak, p.pixels), reverse=True)
    return out[:MAX_PROPOSALS]
