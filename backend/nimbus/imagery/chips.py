"""64×64 chips, reflect-padded, matching training."""

from __future__ import annotations

import numpy as np

from nimbus.imagery import preprocess
from nimbus.imagery.proposals import Proposal

PAD = 32


def pad_image(img: np.ndarray, pad: int = PAD) -> np.ndarray:
    return np.pad(np.asarray(img), pad, mode="reflect")


def crop(padded: np.ndarray, row: int, col: int, chip: int | None = None, pad: int = PAD) -> np.ndarray:
    """``row``/``col`` are in the unpadded image. Pad first; crop without adding pad again.

    Same indexing as the training notebook: ``padded[r:r+64, c:c+64]``.
    """
    chip = preprocess.chip_size() if chip is None else chip
    r = int(row)
    c = int(col)
    return padded[r : r + chip, c : c + chip].copy()


def is_edge(chip: np.ndarray) -> bool:
    ch = np.asarray(chip)
    frac = float((ch <= preprocess.nodata_level()).mean())
    return frac > preprocess.nodata_max_frac()


def extract(img: np.ndarray, items: list[Proposal], valid: np.ndarray | None = None) -> list[tuple[np.ndarray, bool]]:
    """Crop chips. JPEG uses the training no-data-border rule on pixel values.

    GeoTIFF passes the raster valid-mask so clipped sea speckle is not treated
    as a JPEG tile border (that would mark every chip ``edge``).
    """
    padded = pad_image(img)
    valid_padded = None
    if valid is not None:
        valid_padded = np.pad(np.asarray(valid, dtype=np.uint8), PAD, mode="constant", constant_values=0)
    out = []
    for item in items:
        chip = crop(padded, item.row, item.col)
        if valid_padded is None:
            edge = is_edge(chip)
        else:
            vchip = crop(valid_padded, item.row, item.col)
            edge = float((vchip == 0).mean()) > preprocess.nodata_max_frac()
        out.append((chip, edge))
    return out
