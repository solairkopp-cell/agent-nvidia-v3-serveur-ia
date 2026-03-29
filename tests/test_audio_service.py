"""
tests/test_audio_service.py
Tests unitaires de l'AudioService.
Toutes les fonctions sont pures → pas de mock nécessaire.
"""
import numpy as np
import pytest

from services.audio_service import AudioService, TARGET_SAMPLE_RATE


@pytest.fixture
def audio():
    return AudioService()


class TestResample:

    def test_resample_48k_to_16k(self, audio):
        """4800 samples @ 48kHz → 1600 samples @ 16kHz."""
        samples = np.ones(4800, dtype=np.float32)
        result = audio.resample(samples, source_rate=48000, target_rate=16000)
        assert len(result) == 1600
        assert result.dtype == np.float32

    def test_resample_identity(self, audio):
        """Même sample rate → retourner tel quel."""
        samples = np.ones(1600, dtype=np.float32)
        result = audio.resample(samples, source_rate=16000, target_rate=16000)
        np.testing.assert_array_equal(result, samples)

    def test_resample_empty(self, audio):
        """Array vide → retourner array vide."""
        samples = np.array([], dtype=np.float32)
        result = audio.resample(samples, source_rate=48000, target_rate=16000)
        assert len(result) == 0


class TestToMono:

    def test_stereo_to_mono(self, audio):
        """Stéréo (2, N) → mono (N,)."""
        samples = np.ones((2, 1000), dtype=np.float32)
        result = audio.to_mono(samples)
        assert result.ndim == 1
        assert len(result) == 1000

    def test_mono_unchanged(self, audio):
        """Mono (N,) → inchangé."""
        samples = np.ones(1000, dtype=np.float32)
        result = audio.to_mono(samples)
        assert result.ndim == 1
        assert len(result) == 1000


class TestDurationMs:

    def test_duration_1_second(self, audio):
        """16000 samples @ 16kHz → 1000ms."""
        samples = np.zeros(16000, dtype=np.float32)
        assert audio.duration_ms(samples) == pytest.approx(1000.0)

    def test_duration_half_second(self, audio):
        """8000 samples @ 16kHz → 500ms."""
        samples = np.zeros(8000, dtype=np.float32)
        assert audio.duration_ms(samples) == pytest.approx(500.0)


class TestConcat:

    def test_concat_two_arrays(self, audio):
        a = np.ones(100, dtype=np.float32)
        b = np.ones(200, dtype=np.float32) * 2
        result = audio.concat([a, b])
        assert len(result) == 300
        assert result[0] == 1.0
        assert result[100] == 2.0

    def test_concat_empty_list(self, audio):
        result = audio.concat([])
        assert len(result) == 0


class TestWavRoundtrip:

    def test_array_to_wav_and_back(self, audio):
        """numpy → WAV bytes → numpy doit être proche de l'original."""
        original = np.sin(np.linspace(0, 2 * np.pi, 16000)).astype(np.float32)
        wav_bytes = audio.array_to_wav_bytes(original)
        recovered, rate = audio.wav_bytes_to_array(wav_bytes)
        assert rate == TARGET_SAMPLE_RATE
        np.testing.assert_allclose(recovered, original, atol=1e-4)


class TestArrayToAvFrames:

    def test_array_to_av_frames_resamples_and_chunks(self, audio):
        """Le TTS est resamplé vers 16kHz et découpé en frames régulières."""
        pytest.importorskip("av")

        original = np.linspace(-0.5, 0.5, 24000, dtype=np.float32)
        frames = audio.array_to_av_frames(
            original,
            source_rate=24000,
            target_rate=16000,
            frame_ms=20,
        )

        assert frames
        assert all(frame.sample_rate == 16000 for frame in frames)
        assert all(frame.format.name == "s16" for frame in frames)
        assert all(frame.layout.name == "mono" for frame in frames)
        assert sum(frame.samples for frame in frames) == 16000
