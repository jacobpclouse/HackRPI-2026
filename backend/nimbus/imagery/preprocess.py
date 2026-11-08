"""Load ``backend/models/preprocess.json``."""

from __future__ import annotations

import json
from functools import lru_cache

from nimbus import paths


@lru_cache(maxsize=1)
def load() -> dict:
    path = paths.models_dir() / "preprocess.json"
    return json.loads(path.read_text())


def ref_p50() -> float:
    return float(load()["ref_p50"])


def ref_p99() -> float:
    return float(load()["ref_p99"])


def proposal_params() -> dict:
    return dict(load()["proposals"])


def chip_size() -> int:
    return int(load()["chip"])


def nodata_level() -> int:
    return int(load()["nodata_level"])


def nodata_max_frac() -> float:
    return float(load()["nodata_max_frac"])
