# Ship classifier (ResNet-18)

Offline scorer for 64×64 Sentinel-1 VV chips. It does not replace CA-CFAR. CFAR still finds bright returns; this model only says how ship-like a chip looks.

## Architecture and contract

- ResNet-18, single-channel input, one logit out. Normalization is inside the ONNX graph.
- File: `ship_clf_single.onnx`
- Input: `float32` `(N, 1, 64, 64)` in `[0, 1]` (10 m VV intensity, not dB)
- Output: one logit per chip; apply sigmoid for `vessel_score`
- Threshold file: `ship_clf_threshold.json` → `0.784…`, chosen on the validation scene as the **highest threshold that keeps ≥95% of ships**

`darkwatch.detection.classifier` lazy-loads the session. The app starts if the file or `onnxruntime` is missing.

## Training data

[LS-SSDD-v1.0](https://github.com/TianwenZhang0825/LS-SSDD-v1.0-OPEN) (Sentinel-1). Split used here: scenes 1–9 train, scene 10 validation, scenes 11–15 test. Official dataset and manual: that GitHub repo (not the copy that was briefly in this tree).

## Held-out test (scenes 11–15, at the threshold)

| Metric | Value |
| --- | --- |
| Average precision | 0.981 |
| Ships kept | 96.8% |
| CFAR false alarms rejected | 88.6% |
| Open-sea background rejected | 99.5% |

## Kattegat (native 10 m Sentinel-1 RTC)

17 of 18 AIS-matched detections scored above the threshold. The miss is **D015** (HAGLAND PREMIER, 0.5 km from shore, score 0.63).

## Known limits

- Cannot tell a ship from a fixed structure (platform, rock, persistent shoreline clutter).
- Weaker near shore (see D015).
- Trained on 2020 Sentinel-1A/B. The demo scene is Sentinel-1D in 2026.
- Unmatched + vessel-like is not evidence of wrongdoing.

## License

LS-SSDD-v1.0 prohibits commercial use; this model inherits that restriction.

## Citation

Zhang, T. et al. "LS-SSDD-v1.0: A Deep Learning Dataset Dedicated to Small Ship Detection from Large-Scale Sentinel-1 SAR Images." *Remote Sensing* 12(18), 2997 (2020).
