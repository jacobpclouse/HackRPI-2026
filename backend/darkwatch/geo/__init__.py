"""Protected areas and preset ocean regions."""

from darkwatch.geo.mpa import annotate_mpa, fetch_natura2000, fetch_wdpa, simplify_collection
from darkwatch.geo.regions import REGIONS, by_id

__all__ = [
    "REGIONS",
    "annotate_mpa",
    "by_id",
    "fetch_natura2000",
    "fetch_wdpa",
    "simplify_collection",
]
