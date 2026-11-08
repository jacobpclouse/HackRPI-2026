"""AIS sample loading, reporting gaps, the silence-timing baseline, and AISStream cache.

Heavy Danish-AIS helpers are imported lazily so tools like ``record_ais_snapshot``
do not pull in sgp4 / the catalog just to talk to AISStream.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ais_csv_path",
    "ais_silences",
    "annotate_overlap",
    "load_tracks",
    "onset_after_pass",
    "overlap_seconds",
]


def __getattr__(name: str) -> Any:
    if name in {"ais_csv_path", "load_tracks"}:
        from darkwatch.ais.ais_io import ais_csv_path, load_tracks

        values = {"ais_csv_path": ais_csv_path, "load_tracks": load_tracks}
        return values[name]
    if name in {"ais_silences", "annotate_overlap", "onset_after_pass", "overlap_seconds"}:
        from darkwatch.ais.silence import ais_silences, annotate_overlap, onset_after_pass, overlap_seconds

        values = {
            "ais_silences": ais_silences,
            "annotate_overlap": annotate_overlap,
            "onset_after_pass": onset_after_pass,
            "overlap_seconds": overlap_seconds,
        }
        return values[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
