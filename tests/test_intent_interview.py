"""
tests/test_intent_interview.py
Tests unitaires de IntentInterview.
"""
import numpy as np
import pytest

from intent_detection.intent_interview import IntentInterview


class _FakeModel:
    def __init__(self, outputs):
        self._outputs = list(outputs)

    def encode(self, *_args, **_kwargs):
        return self._outputs.pop(0)


def test_classify_uses_numpy_cosine_scores():
    detector = IntentInterview(csv_path="intent_detection/intentions.csv")
    detector._labels = ["A", "B"]
    detector._example_embeddings = np.asarray(
        [
            [1.0, 0.0],
            [0.0, 1.0],
        ],
        dtype=np.float32,
    )
    detector._model = _FakeModel([np.asarray([0.1, 0.9], dtype=np.float32)])

    result = detector.classify("bonjour")

    assert result.intent == "B"
    assert result.score == pytest.approx(0.9)


def test_shutdown_clears_loaded_state():
    detector = IntentInterview(csv_path="intent_detection/intentions.csv")
    detector._labels = ["A"]
    detector._examples = ["hello"]
    detector._example_embeddings = np.asarray([[1.0, 0.0]], dtype=np.float32)
    detector._model = object()

    detector.shutdown()

    assert detector._model is None
    assert detector._example_embeddings is None
    assert detector._labels == []
    assert detector._examples == []
