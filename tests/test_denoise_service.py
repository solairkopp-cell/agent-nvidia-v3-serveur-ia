"""
tests/test_denoise_service.py
Tests unitaires du DenoiseService (DeepFilterNet).
"""
import asyncio

import numpy as np

from services.audio_service import AudioService
from services.denoise_service import DenoiseService


async def _assert_process_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", False)
    service = DenoiseService(audio=AudioService())

    samples = np.asarray([0.1, -0.2, 0.3], dtype=np.float32)
    result = await service.process(samples, sample_rate=16000, state=None)

    np.testing.assert_array_equal(result, samples)


def test_process_passthrough_when_disabled_sync(monkeypatch):
    asyncio.run(_assert_process_passthrough_when_disabled(monkeypatch))


def test_process_uses_deepfilternet_backend(monkeypatch):
    """Test que le process DeepFilterNet retourne un array de même shape."""
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "deepfilternet")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    # Mock du modèle pour éviter de charger le vrai modèle
    service._model = object()
    service._df_state = object()
    
    samples = np.ones(320, dtype=np.float32)
    
    # Mock de _process_deepfilternet pour éviter le vrai traitement
    def mock_process(samples, sample_rate):
        return samples * 0.9  # Simulation simple
    
    service._process_deepfilternet = mock_process
    
    result = service._process_deepfilternet(samples, 16000)
    
    assert result.shape == samples.shape
    assert result.dtype == np.float32


def test_release_stream_state_noop(monkeypatch):
    """DeepFilterNet n'a pas d'état par stream, release_stream_state est no-op."""
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "deepfilternet")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True

    state = service.create_stream_state()
    assert state == {}

    # Ne doit pas lever d'exception
    service.release_stream_state(state)


def test_process_utterance_uses_deepfilternet(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "deepfilternet")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    service._model = object()
    service._df_state = object()
    
    def mock_process(samples, sample_rate):
        return samples * 0.9
    
    service._process_deepfilternet = mock_process

    result = asyncio.run(service.process_utterance(np.ones(320, dtype=np.float32), sample_rate=16000))

    assert result.shape == (320,)
    assert result.dtype == np.float32


def test_process_empty_samples_returns_empty(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True

    samples = np.array([], dtype=np.float32)
    result = asyncio.run(service.process(samples, sample_rate=16000, state=None))

    assert result.size == 0


def test_process_wrong_sample_rate_passthrough(monkeypatch):
    """Si sample_rate != 16000, retourne les samples sans modification."""
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    service._model = object()
    service._df_state = object()

    samples = np.ones(320, dtype=np.float32)
    result = service._process_deepfilternet(samples, sample_rate=48000)

    np.testing.assert_array_equal(result, samples)
