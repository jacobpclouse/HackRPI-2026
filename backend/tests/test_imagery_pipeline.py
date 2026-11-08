"""Imagery pipeline units. No live network."""

import numpy as np
import pytest

from darkwatch.imagery import chips, geotiff, ground_truth, proposals
from darkwatch.imagery.geotiff import parse_acquisition


def _blob_image():
    img = np.full((800, 800), 12, dtype=np.uint8)
    spots = [(120, 140), (400, 410), (650, 200)]
    for r, c in spots:
        img[r : r + 12, c : c + 12] = 255
    return img, spots


def test_proposals_find_three_blobs():
    img, spots = _blob_image()
    found = proposals.proposals(img)
    assert len(found) == 3
    for r, c in spots:
        assert any(abs(p.row - (r + 5.5)) < 4 and abs(p.col - (c + 5.5)) < 4 for p in found)
        hit = min(found, key=lambda p: (p.row - r) ** 2 + (p.col - c) ** 2)
        assert hit.row_min <= r + 2 <= hit.row_max
        assert hit.col_min <= c + 2 <= hit.col_max


def test_edge_flag_on_half_black_chip():
    chip = np.zeros((64, 64), dtype=np.uint8)
    chip[:, 32:] = 80
    assert chips.is_edge(chip)
    sea = np.full((64, 64), 54, dtype=np.uint8)
    assert not chips.is_edge(sea)


def test_ground_truth_tp_fp_fn():
    boxes = [
        ground_truth.GtBox("a", 10, 10, 20, 20),
        ground_truth.GtBox("b", 100, 100, 120, 120),
    ]
    dets = [
        {"id": "U001", "centroid": {"row": 15, "col": 15}},
        {"id": "U002", "centroid": {"row": 50, "col": 50}},
    ]
    out = ground_truth.score(dets, boxes)
    assert out["tp"] == 1
    assert out["fp"] == 1
    assert out["fn"] == 1
    assert out["missed"][0]["name"] == "b"


def test_acquisition_time_sources():
    tag = parse_acquisition({"DARKWATCH_ACQUISITION_TIME": "2026-11-02T05:23:46Z"}, "x.tif", None)
    assert tag["source"] == "geotiff_tag"
    tiff = parse_acquisition({"TIFFTAG_DATETIME": "2026:11:02 05:23:46"}, "x.tif", None)
    assert tiff["source"] == "tiff_datetime"
    name = parse_acquisition({}, "S1D_IW_GRDH_20261102T052346_kattegat_sample.tif", None)
    assert name["source"] == "filename"
    assert name["time"].startswith("2026-11-02T05:23:46")
    user = parse_acquisition({}, "plain.tif", "2026-11-02T05:23:46Z")
    assert user["source"] == "user"


def test_geotiff_spacing_projected_and_geographic(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    proj = tmp_path / "proj.tif"
    with rasterio.open(
        proj,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=1,
        dtype="float32",
        crs="EPSG:32633",
        transform=from_origin(300000, 6300000, 10, 10),
        nodata=-32768,
    ) as dst:
        dst.write(np.full((32, 32), 0.02, dtype=np.float32), 1)
    geo = geotiff.load(proj, filename="proj.tif")
    assert abs(geo.spacing_m - 10) < 0.5
    assert geo.value_type == "linear"

    ll = tmp_path / "ll.tif"
    with rasterio.open(
        ll,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(12.0, 57.0, 0.00009, 0.00009),
        nodata=-32768,
    ) as dst:
        dst.write(np.full((32, 32), 0.02, dtype=np.float32), 1)
    geo_ll = geotiff.load(ll, filename="ll.tif")
    assert geo_ll.spacing_m > 1
    assert geo_ll.bbox is not None
