import numpy as np
import pytest

from services.intent_service import IntentService


class _FakeEmbedder:
    def encode(self, texts, convert_to_numpy=True):
        assert convert_to_numpy is True
        assert isinstance(texts, list)
        return np.asarray([[0.1, 0.2, 0.3]], dtype=np.float32)


class _FakeClassifier:
    def __init__(self, label="show_deliveries", probs=None):
        self._label = label
        self._probs = np.asarray(
            probs if probs is not None else [[0.1, 0.8, 0.1]],
            dtype=np.float32,
        )
        self.classes_ = np.asarray(
            ["show_map", "show_deliveries", "start_navigation"],
            dtype=object,
        )
        self.multi_class = "auto"

    def predict(self, vector):
        assert vector.shape == (1, 3)
        return np.asarray([self._label], dtype=object)

    def predict_proba(self, vector):
        assert vector.shape == (1, 3)
        return self._probs


@pytest.mark.asyncio
async def test_startup_and_getint_use_finetuned_pipeline(monkeypatch):
    service = IntentService()
    monkeypatch.setattr(service, "_load_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(service, "_load_classifier", lambda: _FakeClassifier())

    await service.startup()

    assert await service.health_check() is True
    assert service.getint("show me my deliveries") == "show_deliveries"
    assert service.predict_proba("show me my deliveries")["show_deliveries"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_threshold_returns_unknown_when_confidence_too_low(monkeypatch):
    service = IntentService()
    service._threshold = 0.95
    monkeypatch.setattr(service, "_load_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(
        service,
        "_load_classifier",
        lambda: _FakeClassifier(probs=[[0.2, 0.7, 0.1]]),
    )

    await service.startup()

    assert service.getint("show me my deliveries") == "INCONNU"


@pytest.mark.asyncio
async def test_detect_exposes_intent_and_probabilities(monkeypatch):
    service = IntentService()
    monkeypatch.setattr(service, "_load_embedder", lambda: _FakeEmbedder())
    monkeypatch.setattr(service, "_load_classifier", lambda: _FakeClassifier())

    await service.startup()
    detected = await service.detect("show me my deliveries")

    assert detected.intents == ["show_deliveries"]
    assert detected.raw["intent"] == "show_deliveries"
    assert detected.raw["probabilities"]["show_deliveries"] == pytest.approx(0.8)


def test_blank_text_returns_unknown_without_model_load():
    service = IntentService()
    assert service.getint("   ") == "INCONNU"


def test_non_empty_text_requires_startup():
    service = IntentService()
    with pytest.raises(RuntimeError, match="IntentService not started"):
        service.getint("hello")
