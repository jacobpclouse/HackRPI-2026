"""AIS reporting gaps, and whether they overlap SAR coverage gaps."""

from __future__ import annotations

from datetime import datetime, timedelta

from darkwatch.detection.matching import Fix
from darkwatch.orbit.gaps import Gap
from darkwatch.orbit.passes import Pass


def _inside(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = bbox
    return west <= lon <= east and south <= lat <= north


def ais_silences(
    tracks: dict[str, list[Fix]],
    bbox: tuple[float, float, float, float],
    min_gap_s: float = 1800.0,
) -> list[dict]:
    """Holes between consecutive pings while the vessel is in the bbox."""
    found: list[dict] = []
    for mmsi, fixes in tracks.items():
        ordered = sorted(fixes, key=lambda f: f.t)
        name = ""
        for fix in ordered:
            if fix.name:
                name = fix.name
        for a, b in zip(ordered, ordered[1:], strict=False):
            dt = (b.t - a.t).total_seconds()
            if dt < min_gap_s:
                continue
            if not (_inside(a.lat, a.lon, bbox) or _inside(b.lat, b.lon, bbox)):
                continue
            found.append(
                {
                    "mmsi": mmsi,
                    "name": name or "Unknown",
                    "start": a.t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": b.t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "duration_s": round(dt, 1),
                    "duration_h": round(dt / 3600.0, 2),
                    "lat": round((a.lat + b.lat) / 2, 5),
                    "lon": round((a.lon + b.lon) / 2, 5),
                }
            )
    found.sort(key=lambda row: row["duration_s"], reverse=True)
    return found


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def overlap_seconds(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    start = max(a0, b0)
    end = min(a1, b1)
    return max(0.0, (end - start).total_seconds())


def annotate_overlap(silences: list[dict], gaps: list[Gap]) -> list[dict]:
    annotated = []
    for row in silences:
        a0, a1 = _parse(row["start"]), _parse(row["end"])
        best = 0.0
        best_gap = None
        for gap in gaps:
            seconds = overlap_seconds(a0, a1, gap.start, gap.end)
            if seconds > best:
                best = seconds
                best_gap = gap
        item = dict(row)
        item["overlap_gap_s"] = round(best, 1)
        item["overlaps_coverage_gap"] = best >= 60
        if best_gap is not None and best >= 60:
            item["coverage_gap"] = best_gap.to_dict()
        else:
            item["coverage_gap"] = None
        annotated.append(item)
    annotated.sort(key=lambda r: (r["overlap_gap_s"], r["duration_s"]), reverse=True)
    return annotated


def _when(value) -> datetime:
    return value if isinstance(value, datetime) else _parse(value)


def _pass_end(p: Pass | dict) -> datetime:
    return p.end if isinstance(p, Pass) else _when(p["end"])


def onset_after_pass(
    silences: list[dict],
    passes: list[Pass | dict],
    window_min: float = 30,
    day_start: datetime | None = None,
    day_end: datetime | None = None,
) -> dict:
    """Do AIS silences start soon after a systematic pass ends, more than chance?

    ``observed_rate`` is the fraction of silences (start inside the day) that
    begin within ``window_min`` minutes after a pass ends. ``expected_rate`` is
    the fraction of the day covered by those post-pass windows (overlaps
    merged, clipped to the day): the rate a silence starting at a uniformly
    random time would show. ``p_value`` is a one-sided binomial test.

    Pass only the systematic passes that count toward coverage gaps.
    """
    from scipy.stats import binomtest

    window = timedelta(minutes=window_min)
    ends = sorted(_pass_end(p) for p in passes)
    starts = sorted(_when(row["start"]) for row in silences)
    if day_start is None:
        anchor = (ends or starts or [None])[0]
        if anchor is None:
            return {
                "observed_k": 0,
                "n": 0,
                "observed_rate": None,
                "expected_rate": None,
                "ratio": None,
                "p_value": None,
                "window_min": window_min,
                "significant": False,
            }
        day_start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    if day_end is None:
        day_end = day_start + timedelta(hours=24)

    merged: list[list[datetime]] = []
    for end in ends:
        a, b = max(end, day_start), min(end + window, day_end)
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    covered = sum((b - a).total_seconds() for a, b in merged)
    expected = covered / (day_end - day_start).total_seconds()

    in_day = [t for t in starts if day_start <= t < day_end]
    n = len(in_day)
    k = sum(1 for t in in_day if any(end <= t <= end + window for end in ends))
    observed = k / n if n else None
    p_value = float(binomtest(k, n, expected, alternative="greater").pvalue) if n else None
    return {
        "observed_k": k,
        "n": n,
        "observed_rate": None if observed is None else round(observed, 4),
        "expected_rate": round(expected, 4),
        "ratio": None if observed is None or expected <= 0 else round(observed / expected, 3),
        "p_value": None if p_value is None else round(p_value, 6),
        "window_min": window_min,
        "day_start": day_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day_end": day_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pass_count": len(ends),
        "significant": p_value is not None and p_value <= 0.05,
    }
