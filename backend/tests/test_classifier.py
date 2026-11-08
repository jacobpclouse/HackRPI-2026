"""ONNX ship classifier. Skips if onnxruntime is not installed."""

import numpy as np
import pytest

onnxruntime = pytest.importorskip("onnxruntime")

from darkwatch.detection import classifier  # noqa: E402


def test_score_zero_chips_shape_and_range():
    chips = np.zeros((4, 64, 64), dtype=np.uint8)
    out = classifier.score(chips)
    assert out.shape == (4,)
    assert np.all(out >= 0.0) and np.all(out <= 1.0)


def test_score_rejects_wrong_shape():
    with pytest.raises(ValueError, match="expected"):
        classifier.score(np.zeros((4, 32, 32), dtype=np.uint8))


def test_threshold_is_a_probability():
    value = classifier.threshold()
    assert 0.0 < value < 1.0
