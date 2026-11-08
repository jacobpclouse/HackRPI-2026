"""Steps that build the committed Kattegat demo in data/demo.

Each step takes a ``Target`` (which scene, which AIS day, where to write).
``prepare_demo.py`` runs them in order; the refresh job builds its own Target
and reuses the same steps.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from nimbus import paths  # noqa: E402

logger = logging.getLogger("nimbus.prepare")

SCENE_ID = "S1D_IW_GRDH_1SDV_20261102T052330_20261102T052402_005284_00A0D2_rtc"
SCENE_TIME = datetime(2026, 11, 2, 5, 23, 46, tzinfo=timezone.utc)
BBOX = (11.45, 56.60, 12.30, 57.20)  # west, south, east, north
AIS_URL = "http://aisdata.ais.dk.s3.eu-central-1.amazonaws.com/aisdk-2026-11-02.zip"
NE_URL = "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip"
RES_M = 30.0
STEPS = ("catalog", "scene", "ais", "mpa", "detect")


@dataclass
class Target:
    scene_id: str = SCENE_ID
    scene_time: datetime = SCENE_TIME
    bbox: tuple[float, float, float, float] = BBOX
    ais_url: str = AIS_URL
    out_dir: Path = field(default_factory=paths.demo_dir)
    raw_dir: Path = field(default_factory=paths.raw_dir)
    res_m: float = RES_M
    ne_url: str = NE_URL

    def ais_zip_path(self) -> Path:
        day = self.scene_time.strftime("%Y-%m-%d")
        return self.raw_dir / f"aisdk-{day}.zip"


def log(msg: str) -> None:
    logger.info(msg)
