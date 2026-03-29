"""
tests/test_denoise_service.py
Tests unitaires du DenoiseService.
"""
import asyncio

import numpy as np

from services.audio_service import AudioService
from services.denoise_service import DenoiseService


class _FakeRNNoise:
    def __init__(self, sample_rate):
        self.sample_rate = sample_rate
        self.reset_called = False

    def denoise_chunk(self, chunk, partial=False):
        chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
        out = np.clip(chunk * 0.5, -1.0, 1.0)
        pcm16 = (out * 32767.0).astype(np.int16).reshape(1, -1)
        yield np.asarray([[0.9]], dtype=np.float32), pcm16

    def reset(self):
        self.reset_called = True


async def _assert_process_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", False)
    service = DenoiseService(audio=AudioService())

    samples = np.asarray([0.1, -0.2, 0.3], dtype=np.float32)
    result = await service.process(samples, sample_rate=16000, state=None)

    np.testing.assert_array_equal(result, samples)


def test_process_passthrough_when_disabled_sync(monkeypatch):
    asyncio.run(_assert_process_passthrough_when_disabled(monkeypatch))


def test_process_uses_rnnoise_backend(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "rnnoise")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    service._rnnoise_cls = _FakeRNNoise
    state = service.create_stream_state()
    samples = np.ones(320, dtype=np.float32)

    result = service._process_rnnoise(samples, 16000, state)

    assert result.shape == samples.shape
    assert result.dtype == np.float32
    assert float(np.mean(result)) > 0.49
    assert float(np.mean(result)) < 0.51


def test_release_stream_state_resets_backend(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "rnnoise")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    service._rnnoise_cls = _FakeRNNoise

    state = service.create_stream_state()
    assert state.reset_called is False

    service.release_stream_state(state)

    assert state.reset_called is True


def test_process_utterance_uses_fresh_backend_state(monkeypatch):
    monkeypatch.setattr("config.DENOISE_ENABLED", True)
    monkeypatch.setattr("config.DENOISE_BACKEND", "rnnoise")
    service = DenoiseService(audio=AudioService())
    service._enabled = True
    service._ready = True
    service._rnnoise_cls = _FakeRNNoise

    result = asyncio.run(service.process_utterance(np.ones(320, dtype=np.float32), sample_rate=16000))

    assert result.shape == (320,)
    assert result.dtype == np.float32
