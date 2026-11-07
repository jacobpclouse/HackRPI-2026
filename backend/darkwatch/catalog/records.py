"""Catalog records: OMM parsing, the altitude filter, and Alpha-5 TLE export."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from darkwatch.catalog.families import classify, exclusion_reason
from darkwatch.orbit.orbit import epoch_of, propagate_one, satrec_from_omm, tle_lines


@dataclass
class SatRecord:
    norad: int
    name: str
    family: str
    coverage: str
    look: str
    inc_near: float
    inc_far: float
    access_inc: float
    nominal_width_km: float | None
    color: str
    note: str
    epoch: str
    tle1: str
    tle2: str
    omm: dict

    def to_public(self) -> dict:
        return {
            "norad": self.norad,
            "name": self.name,
            "family": self.family,
            "coverage": self.coverage,
            "look": self.look,
            "inc_near": self.inc_near,
            "inc_far": self.inc_far,
            "access_inc": self.access_inc,
            "nominal_width_km": self.nominal_width_km,
            "color": self.color,
            "note": self.note,
            "epoch": self.epoch,
            "tle1": self.tle1,
            "tle2": self.tle2,
            "label": "possible coverage" if self.coverage == "possible" else "systematic swath geometry",
        }

    def to_blob(self) -> dict:
        return {
            "norad": self.norad,
            "name": self.name,
            "family": self.family,
            "coverage": self.coverage,
            "look": self.look,
            "inc_near": self.inc_near,
            "inc_far": self.inc_far,
            "access_inc": self.access_inc,
            "nominal_width_km": self.nominal_width_km,
            "color": self.color,
            "note": self.note,
            "epoch": self.epoch,
            "tle1": self.tle1,
            "tle2": self.tle2,
            "omm": self.omm,
        }

    @classmethod
    def from_blob(cls, row: dict) -> "SatRecord":
        return cls(
            norad=int(row["norad"]),
            name=row["name"],
            family=row["family"],
            coverage=row["coverage"],
            look=row["look"],
            inc_near=float(row["inc_near"]),
            inc_far=float(row["inc_far"]),
            access_inc=float(row["access_inc"]),
            nominal_width_km=row.get("nominal_width_km"),
            color=row["color"],
            note=row["note"],
            epoch=row["epoch"],
            tle1=row["tle1"],
            tle2=row["tle2"],
            omm=row["omm"],
        )


@dataclass
class Catalog:
    fetched_at: str
    source: str
    satellites: list[SatRecord]
    skipped: list[dict]
    # live (just fetched), cache (fresh local copy), stale-cache, or snapshot (committed fallback)
    origin: str = "live"
    notes: list[str] = field(default_factory=list)

    def get(self, norad: int) -> SatRecord | None:
        for sat in self.satellites:
            if sat.norad == norad:
                return sat
        return None


def _alt_ok(sat) -> tuple[bool, float | None]:
    try:
        when = epoch_of(sat) + timedelta(minutes=30)
        pos = propagate_one(sat, when)
    except Exception:
        return False, None
    if not pos:
        return False, None
    alt = pos["alt_km"]
    return 350.0 <= alt <= 1000.0, alt


def record_from_omm(raw: dict) -> tuple[SatRecord | None, dict | None]:
    name = str(raw.get("OBJECT_NAME") or "").strip()
    try:
        norad = int(raw["NORAD_CAT_ID"])
    except (KeyError, TypeError, ValueError):
        return None, {"name": name, "norad": None, "reason": "missing NORAD id"}
    why = exclusion_reason(name)
    if why:
        return None, {"name": name, "norad": norad, "reason": why}
    spec = classify(name)
    if spec is None:
        return None, {"name": name, "norad": norad, "reason": "name is not a SAR mission in this demo"}
    try:
        sat = satrec_from_omm(raw)
        ok, alt = _alt_ok(sat)
        if not ok:
            return None, {
                "name": name,
                "norad": norad,
                "reason": f"propagated altitude {alt} km is outside the SAR LEO band (350–1000 km)",
            }
        line1, line2 = tle_lines(sat, norad)
        epoch = epoch_of(sat).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception as exc:
        return None, {"name": name, "norad": norad, "reason": f"SGP4 init failed: {exc}"}
    rec = SatRecord(
        norad=norad,
        name=name,
        family=spec.family,
        coverage=spec.coverage,
        look=spec.look,
        inc_near=spec.inc_near,
        inc_far=spec.inc_far,
        access_inc=spec.access_inc,
        nominal_width_km=spec.nominal_width_km,
        color=spec.color,
        note=spec.note,
        epoch=epoch,
        tle1=line1,
        tle2=line2,
        omm=raw,
    )
    return rec, None


def satrec_for(rec: SatRecord):
    return satrec_from_omm(rec.omm)
