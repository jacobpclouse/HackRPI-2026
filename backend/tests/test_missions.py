from datetime import datetime, timezone

from darkwatch.catalog.families import FAMILIES
from darkwatch.catalog.missions import asf_vertex_url, copernicus_browser_url, load_missions


def test_every_catalog_family_has_a_registry_entry():
    registry = load_missions()
    families = {spec.family for _, spec in FAMILIES}
    missing = families - set(registry)
    extra = set(registry) - families
    assert not missing, f"missions.json missing families: {sorted(missing)}"
    assert not extra, f"missions.json has unknown families: {sorted(extra)}"


def test_registry_fields_and_access_values():
    allowed = {"open", "open-sample", "restricted", "commercial"}
    for family, spec in load_missions().items():
        assert spec["name"]
        assert spec["band"]
        assert spec["coverage"] in {"systematic", "tasked"}
        assert spec["access"] in allowed, family
        assert spec["links"], family
        for link in spec["links"]:
            assert link["url"].startswith("http"), link
        assert "verified_at" in spec


def test_new_sar_names_classify_and_optical_lookalikes_do_not():
    from darkwatch.catalog.families import classify, exclusion_reason

    assert classify("ARIRANG-5 (KOMPSAT-5)").family == "KOMPSAT-5"
    assert classify("KOMPSAT-3A") is None
    assert classify("JILIN-1 GAOFEN 3A") is None
    assert classify("GAOFEN-3 02").family == "Gaofen-3"
    assert classify("NOVASAR 1").family == "NovaSAR"
    assert classify("STRIX-1").family == "StriX"
    assert classify("QPS-SAR-5 (TSUKUYOMI-I)").family == "QPS-SAR"
    assert classify("ASNARO") is None
    assert classify("ASNARO-2").family == "ASNARO-2"
    assert classify("MARISAT 1") is None
    assert classify("RISAT-2B").family == "RISAT-2"
    assert classify("EOS-4").family == "EOS-04"
    assert classify("HAIYANG-3A").family == "Haiyang-3"
    assert classify("PIESAT-1 A").family == "PIESAT"
    assert "RISAT-1" in (exclusion_reason("RISAT-1") or "")


def test_sentinel1_deep_links_include_point_and_window():
    when = datetime(2026, 11, 2, 5, 23, 46, tzinfo=timezone.utc)
    cop = copernicus_browser_url(56.9, 11.875, when)
    assert "datasetId=S1_CDAS_IW_VVVH" in cop
    assert "lat=56.90000" in cop
    assert "fromTime=2026-11-01" in cop
    assert "toTime=2026-11-03" in cop
    vertex = asf_vertex_url(56.9, 11.875, when)
    assert "dataset=SENTINEL-1" in vertex
    assert "start=2026-11-01" in vertex
    assert "11.87500%2C56.90000" in vertex or "11.87500,56.90000" in vertex
