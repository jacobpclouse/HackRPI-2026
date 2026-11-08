"""Record a real AISStream snapshot into data/demo/ais_global_seed.json.

  PYTHONPATH=backend .venv/bin/python backend/scripts/record_ais_snapshot.py --minutes 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_VENV_HINT = (
    "Use the project venv, not conda/system Python:\n"
    "  PYTHONPATH=backend .venv/bin/python backend/scripts/record_ais_snapshot.py --minutes 10\n"
)

try:
    from nimbus import config, paths  # noqa: E402
    from nimbus.ais import global_cache  # noqa: E402
    from nimbus.ais.stream import pull  # noqa: E402
except ModuleNotFoundError as exc:
    sys.stderr.write(f"{exc}\n{_VENV_HINT}")
    raise SystemExit(1) from exc


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=10)
    parser.add_argument("--out", default=str(paths.ais_global_seed()))
    args = parser.parse_args()
    key = config.aisstream_api_key()
    if not key:
        print("AISSTREAM_API_KEY is unset", file=sys.stderr)
        return 1
    listen_s = max(1.0, args.minutes * 60)
    print(f"listening {listen_s:.0f}s", flush=True)

    def progress(reports: int, unique: int) -> None:
        print(f"reports={reports} unique={unique}", flush=True)

    result = await pull(key, listen_s, on_progress=progress)
    if result.error:
        print(f"error: {result.error}", file=sys.stderr)
    ships = result.ships
    n_reports = result.n_position_reports
    print(f"reports={n_reports} unique={len(ships)}", flush=True)
    if not ships:
        print("no ships recorded; not writing", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    merged = global_cache.merge(ships, {}, now, config.ais_global_max_age_h(), config.ais_global_max_ships())
    state = global_cache.CacheState(
        ships=merged,
        fetched_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        source="seed",
        last_error=None,
        excluded_bbox=global_cache.excluded_bbox(),
    )
    out = Path(args.out)
    global_cache.atomic_write(out, global_cache.to_payload(state))
    print(f"wrote {len(merged)} ships to {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
