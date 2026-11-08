#!/usr/bin/env python3
"""Build the committed Kattegat demo: Sentinel-1 RTC chip, Danish AIS, CFAR, MPAs.

Re-runnable. Skips steps whose outputs already exist unless --force is passed.
The AIS zip is large (~550 MB); it is filtered and not committed.

    python backend/scripts/prepare_demo.py
    python backend/scripts/prepare_demo.py --only scene
    python backend/scripts/prepare_demo.py --skip catalog
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

from nimbus import config, paths  # noqa: E402

config.configure_gdal()

from prepare import STEPS, Target  # noqa: E402
from prepare.ais_step import run as run_ais  # noqa: E402
from prepare.catalog_step import run as run_catalog  # noqa: E402
from prepare.detect_step import run as run_detect  # noqa: E402
from prepare.mpa_step import run as run_mpa  # noqa: E402
from prepare.scene_step import run as run_scene  # noqa: E402


def _wanted(only: str | None, skip: list[str]) -> list[str]:
    skip_set = {s.strip() for s in skip if s.strip()}
    unknown = (skip_set | ({only} if only else set())) - set(STEPS)
    if unknown:
        raise SystemExit(f"unknown step(s) {sorted(unknown)}; choose from {', '.join(STEPS)}")
    if only:
        return [only]
    return [step for step in STEPS if step not in skip_set]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ais-zip", default=config.ais_zip() or str(paths.raw_dir() / "aisdk-2026-11-02.zip"))
    parser.add_argument("--only", choices=STEPS, help="run a single step")
    parser.add_argument("--skip", action="append", default=[], help="skip a step (repeatable)")
    parser.add_argument("--skip-catalog", action="store_true", help="alias for --skip catalog")
    args = parser.parse_args()
    if args.skip_catalog:
        args.skip.append("catalog")

    wanted = _wanted(args.only, args.skip)
    target = Target()
    target.out_dir.mkdir(parents=True, exist_ok=True)
    target.raw_dir.mkdir(parents=True, exist_ok=True)

    if "catalog" in wanted:
        run_catalog(target, force=args.force)
    if "scene" in wanted:
        run_scene(target, force=args.force)
    if "ais" in wanted:
        run_ais(target, zip_path=Path(args.ais_zip), force=args.force)
    if "mpa" in wanted:
        run_mpa(target, force=args.force)
    if "detect" in wanted:
        run_detect(target, force=args.force)


if __name__ == "__main__":
    main()
