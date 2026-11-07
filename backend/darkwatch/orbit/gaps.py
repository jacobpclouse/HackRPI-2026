"""Coverage gaps are the holes between pass windows. Nothing here is a fixed duration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from darkwatch.orbit.passes import Pass


@dataclass
class Gap:
    start: datetime
    end: datetime
    duration_s: float

    def to_dict(self) -> dict:
        hours = self.duration_s / 3600.0
        return {
            "start": self.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": self.end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_s": round(self.duration_s, 1),
            "duration_h": round(hours, 2),
            "label": _label(self.duration_s),
        }


def _label(seconds: float) -> str:
    if seconds >= 3600:
        return f"no systematic swath for {seconds / 3600:.1f} h"
    minutes = max(1, int(round(seconds / 60.0)))
    return f"no systematic swath for {minutes} min"


def merge_windows(passes: list[Pass]) -> list[tuple[datetime, datetime]]:
    ordered = sorted(passes, key=lambda p: p.start)
    merged: list[list[datetime]] = []
    for p in ordered:
        if not merged or p.start > merged[-1][1]:
            merged.append([p.start, p.end])
        elif p.end > merged[-1][1]:
            merged[-1][1] = p.end
    return [(a, b) for a, b in merged]


def coverage_gaps(passes: list[Pass], t0: datetime, t1: datetime) -> list[Gap]:
    """Gaps inside [t0, t1] where no pass window is active.

    Passes should already be filtered to the coverage class you care about.
    """
    if t1 <= t0:
        return []
    windows = []
    for start, end in merge_windows(passes):
        a = max(start, t0)
        b = min(end, t1)
        if b > a:
            windows.append((a, b))
    gaps: list[Gap] = []
    cursor = t0
    for start, end in windows:
        if start > cursor:
            gaps.append(Gap(cursor, start, (start - cursor).total_seconds()))
        cursor = max(cursor, end)
    if cursor < t1:
        gaps.append(Gap(cursor, t1, (t1 - cursor).total_seconds()))
    return gaps


def longest_gap(gaps: list[Gap]) -> Gap | None:
    if not gaps:
        return None
    return max(gaps, key=lambda g: g.duration_s)


def clip_passes(passes: list[Pass], t0: datetime, t1: datetime) -> list[Pass]:
    out = []
    for p in passes:
        if p.end <= t0 or p.start >= t1:
            continue
        out.append(p)
    return out


def hours_between(t0: datetime, t1: datetime) -> float:
    return (t1 - t0) / timedelta(hours=1)
