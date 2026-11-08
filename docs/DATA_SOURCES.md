# Data sources

What DarkWatch reads, what it needs to get it, and whether the packaged demo uses it. URLs that 404'd during this pass were dropped rather than invented. `verified_at` in `backend/darkwatch/catalog/missions.json` is the date a link was last fetched successfully; `null` means it was not checked in this pass.

## Orbits

| Source | Use | Access | License / terms (summary) | Status |
| --- | --- | --- | --- | --- |
| [CelesTrak GP](https://celestrak.org) (OMM JSON) | Live SAR catalog, SGP4 / satellite.js | None | Public GP elements; CelesTrak terms | Used. Classic `FORMAT=TLE` is empty for catalog numbers above 99999; DarkWatch ingests OMM and writes Alpha-5 two-line elements for the browser. |
| [Space-Track.org](https://www.space-track.org) | Authoritative GP history | Free account | Space-Track user agreement | Not used. Candidate for historical pass reconstruction. |

## SAR imagery

Mission pages and catalogs are in `backend/darkwatch/catalog/missions.json`. Access chips in the UI: `OPEN`, `SAMPLE`, `RESTRICTED`, `COMMERCIAL`.

| Family | Band | Access | Where |
| --- | --- | --- | --- |
| Sentinel-1 (ESA/Copernicus) | C | open | [Copernicus Browser](https://browser.dataspace.copernicus.eu) (deep links with `lat`, `lng`, `fromTime`, `toTime`, `datasetId=S1_CDAS_IW_VVVH` are documented); [ASF Vertex](https://search.asf.alaska.edu) (`dataset`, `start`, `end`); [Planetary Computer sentinel-1-rtc](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc) |
| NISAR (NASA/ISRO) | L + S | open | [ASF Vertex](https://search.asf.alaska.edu); [mission page](https://nisar.jpl.nasa.gov) |
| ALOS-2 / ALOS-4 (JAXA) | L | restricted, some open products | [G-Portal](https://gportal.jaxa.jp); [EORC](https://www.eorc.jaxa.jp/ALOS/en/) — not fetched this pass |
| RCM (CSA) | C | restricted | [EODMS](https://www.eodms-sgdot.nrcan-rncan.gc.ca) — not fetched this pass |
| RADARSAT-2 (MDA) | C | commercial | EODMS (above); [MDA Earth observation](https://mda.space/earth-and-space-observation) |
| SAOCOM (CONAE) | L | restricted, ESA third-party | [CONAE catalog](https://catalogos.conae.gov.ar) — not fetched this pass |
| TerraSAR-X / TanDEM-X / PAZ | X | commercial, ESA third-party | [ESA Earth Online](https://earth.esa.int) — not fetched this pass |
| COSMO-SkyMed / CSG (ASI) | X | commercial | [ASI](https://www.asi.it/en/earth-science/cosmo-skymed/); [e-GEOS](https://www.e-geos.it/en/satellite-data/cosmo-skymed-constellation/) |
| ICEYE | X | commercial | [iceye.com](https://www.iceye.com) — not fetched this pass |
| Capella Space | X | open-sample | [AWS Open Data](https://registry.opendata.aws/capella_opendata/) (CC BY 4.0) |
| Umbra | X | open-sample | [AWS Open Data](https://registry.opendata.aws/umbra-open-data/) (CC BY 4.0) |
| KOMPSAT-5 | X | restricted | [ESA KOMPSAT-5](https://earth.esa.int/eogateway/missions/kompsat-5) |
| NovaSAR-1 | S | restricted | [SSTL](https://www.sstl.co.uk/missions/novasar-1) |
| RISAT-2B class | X | restricted | ISRO |
| EOS-04 | C | restricted | ISRO |
| ASNARO-2 | X | commercial | JAXA / NEC |
| StriX | X | commercial | [Synspective](https://synspective.com) |
| QPS-SAR | X | commercial | [iQPS](https://i-qps.com) |
| Gaofen-3 | C | restricted | CNSA |
| Haiyang-3 | C | restricted | NSOAS |
| PIESAT (Hongtu) | X | commercial | [PIESAT](https://www.piesat.cn) |

Also:

| Source | Use | Access | Status |
| --- | --- | --- | --- |
| Microsoft Planetary Computer `sentinel-1-rtc` | Packaged Kattegat chip (VV). Demo CFAR used a 30 m resample; classifier chips and persistence strips used native 10 m | None (SAS-signed COG, no account) | Used |
| Google Earth Engine `COPERNICUS/S1_GRD` | Analysis-ready Sentinel-1 | Free account | Reserved |

## AIS (ship positions)

| Source | Use | Access | License / terms (summary) | Status |
| --- | --- | --- | --- | --- |
| Danish Maritime Authority historical AIS, [aisdata.ais.dk](http://aisdata.ais.dk) | Matching the 2 Nov 2026 scene | None | Public historical AIS | Used. The HTTPS site presented an expired TLS certificate when the demo was built, so the HTTP S3 listing was used. Day zips are ~550 MB; only the filtered sample is committed. |
| NOAA / BOEM [MarineCadastre AIS](https://hub.marinecadastre.gov) | US waters, historical | None | Public | Not used |
| [Global Fishing Watch APIs](https://globalfishingwatch.org/our-apis/) | Validation (`/api/validation/gfw`), vessel presence | Free token, non-commercial | GFW API terms | Optional. Off when `GFW_API_TOKEN` is unset. |
| [AISStream](https://aisstream.io) | Global self-reported AIS context on the globe (`/api/ships/global`) | Free key (`AISSTREAM_API_KEY`) | AISStream terms; no SLA; terrestrial-station coverage, best-effort latency | Used when the key is set and `AIS_GLOBAL_REFRESH=1`. Direct browser connections are not allowed. The server listens on the world stream, writes `data/cache/ais_global.json` (gitignored), and falls back to `data/demo/ais_global_seed.json`. A refresh that returns fewer than 500 position reports, or that would cut the fleet in half, is discarded and the last good cache is kept. Global ships exclude the Kattegat scene bbox from `scene_meta.json` plus 0.05°. They are context only — not radar-verified. |

## Context layers

| Source | Use | Access | Status |
| --- | --- | --- | --- |
| [Protected Planet / WDPA](https://www.protectedplanet.net) | Global protected areas | Token for API | Optional in `scripts/fetch_mpas.py`. Demo uses Natura 2000 instead. |
| EEA Natura 2000 | Packaged MPA polygons around the Kattegat chip | None (MapServer) | Used (75 sites in `data/demo/mpas.geojson`) |
| [Marine Regions](https://www.marineregions.org) EEZ boundaries | Later: distance to EEZ | Free | Not used |
| [Natural Earth](https://www.naturalearthdata.com) 10 m land | Land mask for CFAR | Public domain / Natural Earth terms | Used |

## Ship detection training data

CA-CFAR is still the detector. The ResNet-18 chip classifier was trained on LS-SSDD-v1.0 and is shipped as ONNX. The `Detector` protocol and `xview3_adapter` seam remain in `backend/darkwatch/detection/`.

| Source | Use | Access | License / terms (summary) | Status |
| --- | --- | --- | --- | --- |
| [LS-SSDD-v1.0](https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN) | Train/val/test for the ship-vs-clutter classifier (scenes 1–9 / 10 / 11–15) | [Google Drive](https://drive.google.com/file/d/1-fSKYsKr5wuYuXJE2CDX_Yfr4Ylwjfqm/view?usp=sharing) linked from the official GitHub repo | Non-commercial. The shipped model inherits that restriction. Citation: Zhang, T. et al., *Remote Sensing* 12(18), 2997 (2020). | Used |
| Microsoft Planetary Computer `sentinel-1-rtc` | Native 10 m VV for Kattegat classifier chips and unmatched-detection persistence strips | None | PC terms | Used |
| [xView3-SAR](https://iuu.xview.us) | Dark vessel detection on Sentinel-1 | Free account | xView3 terms | Reserved (`xview3_adapter` seam) |
| SSDD | SAR Ship Detection Dataset | Paper | Zhang et al., Remote Sensing 2021 | Not used |
| HRSID | High-Resolution SAR Images Dataset (Wei et al.) | Paper | — | Not used |
| OpenSARShip | Sentinel-1 ship chips with AIS labels (Huang et al.) | Paper | — | Not used |

Do not treat an unmatched CFAR return as a training label for "dark vessel" in the criminal sense. Unmatched means not matched to public AIS.
