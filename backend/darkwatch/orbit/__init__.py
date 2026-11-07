"""Orbit propagation, swath geometry, pass prediction, and coverage gaps."""

# catalog and orbit import each other's leaf modules (never these re-exports),
# so either package can be imported first.
from darkwatch.orbit.gaps import Gap, clip_passes, coverage_gaps, hours_between, longest_gap, merge_windows
from darkwatch.orbit.geometry import (
    along_cross_km,
    along_cross_km_many,
    bearing_deg,
    destination,
    ground_range_km,
    haversine_km,
    headings_deg,
    wrap_lon,
)
from darkwatch.orbit.orbit import (
    alpha5,
    ensure_utc,
    epoch_of,
    parse_time,
    propagate_many,
    propagate_one,
    satrec_from_omm,
    tle_lines,
)
from darkwatch.orbit.passes import (
    Pass,
    display_ranges_km,
    find_passes,
    in_swath,
    next_pass_over_polygon,
    predict_passes,
    spec_of,
    swath_polygon,
)

__all__ = [
    "Gap",
    "Pass",
    "along_cross_km",
    "along_cross_km_many",
    "alpha5",
    "bearing_deg",
    "clip_passes",
    "coverage_gaps",
    "destination",
    "display_ranges_km",
    "ensure_utc",
    "epoch_of",
    "find_passes",
    "ground_range_km",
    "haversine_km",
    "headings_deg",
    "hours_between",
    "in_swath",
    "longest_gap",
    "merge_windows",
    "next_pass_over_polygon",
    "parse_time",
    "predict_passes",
    "propagate_many",
    "propagate_one",
    "satrec_from_omm",
    "spec_of",
    "swath_polygon",
    "tle_lines",
    "wrap_lon",
]
