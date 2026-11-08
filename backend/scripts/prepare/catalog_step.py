"""Refresh the CelesTrak SAR catalog into data/cache (and the snapshot on force)."""

from __future__ import annotations

from prepare import Target, log


def run(_target: Target | None = None, *, force: bool = False) -> dict:
    from nimbus.catalog import get_catalog

    log("refreshing CelesTrak SAR catalog")
    cat = get_catalog(refresh=True)
    families: dict[str, int] = {}
    for sat in cat.satellites:
        families[sat.family] = families.get(sat.family, 0) + 1
    log(f"catalog {len(cat.satellites)} sats at {cat.fetched_at}: {families}")
    log(f"skipped {len(cat.skipped)}")
    if force:
        from nimbus.catalog import snapshot_path, write

        write(snapshot_path(), cat)
        log(f"wrote snapshot {snapshot_path()}")
    return {
        "count": len(cat.satellites),
        "fetched_at": cat.fetched_at,
        "origin": cat.origin,
        "families": families,
        "skipped": len(cat.skipped),
    }
