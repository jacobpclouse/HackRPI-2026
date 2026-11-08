import random
from datetime import datetime, timedelta, timezone

from nimbus.ais import onset_after_pass
from nimbus.orbit import Pass

DAY0 = datetime(2026, 11, 2, tzinfo=timezone.utc)
DAY1 = DAY0 + timedelta(hours=24)


def _passes(hours: list[float]) -> list[Pass]:
    out = []
    for h in hours:
        center = DAY0 + timedelta(hours=h)
        out.append(
            Pass(1, "S1", "Sentinel-1", "systematic", center - timedelta(seconds=25), center + timedelta(seconds=25), center, 100, 700, "#fff")
        )
    return out


def _silence(start: datetime) -> dict:
    return {"start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_silences_right_after_passes_are_significant():
    passes = _passes([1, 5, 9, 13, 17, 21])
    silences = [_silence(p.end + timedelta(minutes=5)) for p in passes for _ in range(3)]
    out = onset_after_pass(silences, passes, window_min=30, day_start=DAY0, day_end=DAY1)
    assert out["n"] == 18
    assert out["observed_k"] == 18
    assert out["observed_rate"] == 1.0
    # Six 30-minute windows over 24 h.
    assert abs(out["expected_rate"] - 6 * 0.5 / 24) < 1e-3
    assert out["p_value"] < 1e-6
    assert out["significant"] is True
    assert out["ratio"] > 5


def test_uniform_random_silences_are_not_significant():
    rng = random.Random(7)
    passes = _passes([1, 5, 9, 13, 17, 21])
    silences = [_silence(DAY0 + timedelta(seconds=rng.uniform(0, 86400 - 1))) for _ in range(60)]
    out = onset_after_pass(silences, passes, window_min=30, day_start=DAY0, day_end=DAY1)
    assert out["n"] == 60
    assert out["p_value"] > 0.05
    assert out["significant"] is False


def test_overlapping_windows_are_merged_and_clipped():
    # Two passes 10 min apart share most of their window; one ends 10 min before midnight.
    passes = _passes([3, 3 + 10 / 60, 24 - 10 / 60])
    out = onset_after_pass([], passes, window_min=30, day_start=DAY0, day_end=DAY1)
    covered_min = out["expected_rate"] * 24 * 60
    assert abs(covered_min - (40 + 10 - 25 / 60)) < 0.5
    assert out["n"] == 0
    assert out["p_value"] is None


def test_silences_outside_the_day_are_ignored():
    passes = _passes([2])
    silences = [_silence(DAY0 - timedelta(hours=2)), _silence(DAY0 + timedelta(hours=2, minutes=10))]
    out = onset_after_pass(silences, passes, window_min=30, day_start=DAY0, day_end=DAY1)
    assert out["n"] == 1
    assert out["observed_k"] == 1
