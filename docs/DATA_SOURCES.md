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

Also:

| Source | Use | Access | Status |
| --- | --- | --- | --- |
| Microsoft Planetary Computer `sentinel-1-rtc` | Packaged Kattegat chip (VV, 30 m) | None (SAS-signed COG, no account) | Used |
| Google Earth Engine `COPERNICUS/S1_GRD` | Analysis-ready Sentinel-1 | Free account | Reserved |

## AIS (ship positions)

| Source | Use | Access | License / terms (summary) | Status |
| --- | --- | --- | --- | --- |
| Danish Maritime Authority historical AIS, [aisdata.ais.dk](http://aisdata.ais.dk) | Matching the 2 Nov 2026 scene | None | Public historical AIS | Used. The HTTPS site presented an expired TLS certificate when the demo was built, so the HTTP S3 listing was used. Day zips are ~550 MB; only the filtered sample is committed. |
| NOAA / BOEM [MarineCadastre AIS](https://hub.marinecadastre.gov) | US waters, historical | None | Public | Not used |
| [Global Fishing Watch APIs](https://globalfishingwatch.org/our-apis/) | Validation (`/api/validation/gfw`), vessel presence | Free token, non-commercial | GFW API terms | Optional. Off when `GFW_API_TOKEN` is unset. |
| [AISStream](https://aisstream.io) | Live global AIS over WebSocket | Free key | AISStream terms | Not used. Candidate for a live layer. |

## Context layers

| Source | Use | Access | Status |
| --- | --- | --- | --- |
| [Protected Planet / WDPA](https://www.protectedplanet.net) | Global protected areas | Token for API | Optional in `scripts/fetch_mpas.py`. Demo uses Natura 2000 instead. |
| EEA Natura 2000 | Packaged MPA polygons around the Kattegat chip | None (MapServer) | Used (75 sites in `data/demo/mpas.geojson`) |
| [Marine Regions](https://www.marineregions.org) EEZ boundaries | Later: distance to EEZ | Free | Not used |
| [Natural Earth](https://www.naturalearthdata.com) 10 m land | Land mask for CFAR | Public domain / Natural Earth terms | Used |

## Ship detection training data (reserved for the ML phase)

Listed only. DarkWatch's detector today is CA-CFAR. The `Detector` protocol and `xview3_adapter` seam are in `backend/darkwatch/detection/`.

| Source | Notes |
| --- | --- |
| [xView3-SAR](https://iuu.xview.us) | Dark vessel detection on Sentinel-1. Free account. |
| SSDD | SAR Ship Detection Dataset. Official paper: Zhang et al., "SAR Ship Detection Dataset (SSDD): Official Release and Comprehensive Data Analysis", Remote Sensing 2021. |
| HRSID | High-Resolution SAR Images Dataset (Wei et al.). |
| OpenSARShip | Sentinel-1 ship chips with AIS labels (Huang et al.). |
| Our AIS-matched detections | Planned weak labels: matched = ship. Not a substitute for a labeled benchmark. |

Do not treat an unmatched CFAR return as a training label for "dark vessel" in the criminal sense. Unmatched means not matched to public AIS.
