# Imagery samples

## LS-SSDD tiles (`lsssdd/`)

JPEG chips and Pascal VOC XML from [LS-SSDD-v1.0](https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN) test scenes **11–15**. These images were held out of DarkWatch classifier training.

The Analyze gallery lists `11_10_10` and `12_6_30`. The other four tiles (`11_10_13`, `11_10_28`, `11_11_25`, `15_15_22`) live in `lsssdd/held/` — the proposer+classifier misses labeled ships on those chips, so they are kept off the default sample list.

License: non-commercial use only, as stated by LS-SSDD-v1.0. Cite Zhang et al., LS-SSDD-v1.0, if you reuse the tiles.

## GeoTIFF (`geotiff/`)

`S1D_IW_GRDH_20261102T052346_kattegat_sample.tif` is a ~20 km VV Sentinel-1 RTC chip at 10 m over the Kattegat, linear gamma-nought, tagged `DARKWATCH_ACQUISITION_TIME=2026-11-02T05:23:46Z`.

Source: Microsoft Planetary Computer collection `sentinel-1-rtc`, item `S1D_IW_GRDH_1SDV_20261102T052330_20261102T052402_005284_00A0D2_rtc`. Contains modified Copernicus Sentinel data 2026, processed by ESA.
