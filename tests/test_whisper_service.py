import numpy as np

from services.whisper_service import _resample_for_whisper


class TestWhisperResample:

    def test_resample_48k_to_16k(self):
        samples = np.ones(4800, dtype=np.float32)

        result = _resample_for_whisper(samples, 48000, 16000)

        assert result.dtype == np.float32
        assert len(result) == 1600

    def test_resample_identity(self):
        samples = np.linspace(-0.25, 0.25, 1600, dtype=np.float32)

        result = _resample_for_whisper(samples, 16000, 16000)

        np.testing.assert_array_equal(result, samples)
