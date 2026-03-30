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


def test_find_local_snapshot_uses_main_ref(tmp_path):
    hub_root = tmp_path / "huggingface" / "hub"
    repo_dir = hub_root / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
    snap = repo_dir / "snapshots" / "rev123"
    snap.mkdir(parents=True)
    (repo_dir / "refs").mkdir(parents=True)
    (repo_dir / "refs" / "main").write_text("rev123", encoding="utf-8")

    found = IntentInterview._find_local_snapshot(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        cache_dir=str(tmp_path / "huggingface"),
    )

    assert found == snap


def test_resolve_model_source_prefers_explicit_local_dir(tmp_path):
    local_dir = tmp_path / "intent-model"
    local_dir.mkdir()

    detector = IntentInterview(
        csv_path="intent_detection/intentions.csv",
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        local_dir=str(local_dir),
    )

    source, local_only = detector._resolve_model_source()

    assert source == str(local_dir)
    assert local_only is True
