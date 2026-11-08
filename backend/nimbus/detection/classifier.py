"""ResNet-18 ship-vs-clutter scorer. Does not replace CA-CFAR.

CFAR still proposes detections. This module scores 64×64 VV chips. The ONNX
session is loaded on first ``score`` call. ``available()`` is False when
onnxruntime is missing or the model file is not on disk, so the app can start
without the classifier.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from nimbus import paths

MODEL_NAME = "ship_clf_single.onnx"
THRESHOLD_NAME = "ship_clf_threshold.json"
CHIP = 64

_session = None
_input_name: str | None = None


def model_path():
    return paths.models_dir() / MODEL_NAME


def threshold_path():
    return paths.models_dir() / THRESHOLD_NAME


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return model_path().is_file()


@lru_cache(maxsize=1)
def threshold() -> float:
    import json

    path = threshold_path()
    if not path.is_file():
        raise FileNotFoundError(f"Classifier threshold file missing: {path}")
    data = json.loads(path.read_text())
    return float(data["threshold"])


def _session_and_name():
    global _session, _input_name
    if _session is None:
        import onnxruntime as ort

        path = model_path()
        if not path.is_file():
            raise FileNotFoundError(f"Classifier ONNX missing: {path}")
        _session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        _input_name = _session.get_inputs()[0].name
    return _session, _input_name


def _as_nchw(chips: np.ndarray) -> np.ndarray:
    arr = np.asarray(chips)
    if arr.ndim == 3:
        if arr.shape[1:] != (CHIP, CHIP):
            raise ValueError(f"expected (N, {CHIP}, {CHIP}) or (N, 1, {CHIP}, {CHIP}), got {arr.shape}")
        arr = arr[:, None, :, :]
    elif arr.ndim == 4:
        if arr.shape[1:] != (1, CHIP, CHIP):
            raise ValueError(f"expected (N, {CHIP}, {CHIP}) or (N, 1, {CHIP}, {CHIP}), got {arr.shape}")
    else:
        raise ValueError(f"expected (N, {CHIP}, {CHIP}) or (N, 1, {CHIP}, {CHIP}), got {arr.shape}")
    if arr.dtype == np.uint8:
        return arr.astype(np.float32) / 255.0
    return np.clip(arr.astype(np.float32), 0.0, 1.0)


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-logits))


def score(chips: np.ndarray) -> np.ndarray:
    """Return sigmoid probabilities, shape ``(N,)``, values in ``[0, 1]``.

    Accepts uint8 ``(N, 64, 64)`` or float ``(N, 1, 64, 64)`` in ``[0, 1]``.
    """
    batch = _as_nchw(chips)
    session, name = _session_and_name()
    logits = session.run(None, {name: batch})[0]
    probs = _sigmoid(np.asarray(logits, dtype=np.float64).reshape(-1))
    return np.clip(probs, 0.0, 1.0)


class ShipClassifier:
    """Chip scorer behind the same lazy-load helpers. Not a ``Detector``."""

    def available(self) -> bool:
        return available()

    def threshold(self) -> float:
        return threshold()

    def score(self, chips: np.ndarray) -> np.ndarray:
        return score(chips)
