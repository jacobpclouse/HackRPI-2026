"""Protected areas, packaged Natural Earth layers, and preset ocean regions."""

from nimbus.geo.mpa import annotate_mpa, fetch_natura2000, fetch_wdpa, simplify_collection
from nimbus.geo.reference import available as reference_available
from nimbus.geo.reference import jurisdiction, nearest_ports
from nimbus.geo.regions import REGIONS, by_id

__all__ = [
    "REGIONS",
    "annotate_mpa",
    "by_id",
    "fetch_natura2000",
    "fetch_wdpa",
    "jurisdiction",
    "nearest_ports",
    "reference_available",
    "simplify_collection",
]
