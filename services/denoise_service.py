"""
services/denoise_service.py
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import TYPE_CHECKING

import numpy as np

import config

if TYPE_CHECKING:
    from services.audio_service import AudioService


logger = logging.getLogger(__name__)


class DenoiseService:
    def __init__(self, audio: "AudioService"):
        self.audio = audio
        self._enabled: bool = bool(getattr(config, "DENOISE_ENABLED", False))
        self._stream_sample_rate: int = int(config.SAMPLE_RATE)
        self._ready: bool = False
        self._model = None

    async def startup(self) -> None:
        if not self._enabled:
            logger.info("Denoise disabled")
            return
        try:
            await asyncio.to_thread(self._init_rnnoise)
            self._ready = True
            logger.info("Denoise backend ready backend=rnnoise")
        except Exception:
            self._ready = False
            logger.exception("Denoise startup failed; passthrough mode enabled")

    async def shutdown(self) -> None:
        self._ready = False
        self._model = None
        gc.collect()

    def create_stream_state(self):
        if not self._ready or self._model is None:
            return None
        try:
            return self._model.create_state()
        except Exception:
            return None

    def release_stream_state(self, state) -> None:
        pass

    async def process(self, samples: np.ndarray, *, sample_rate: int, state=None) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples
        if not self._enabled or not self._ready:
            return samples
        try:
            return await asyncio.to_thread(self._process_rnnoise, samples, state)
        except Exception:
            logger.exception("Denoise processing failed; passthrough current chunk")
            return samples

    async def process_utterance(self, samples: np.ndarray, *, sample_rate: int) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples
        if not self._enabled or not self._ready:
            return samples
        try:
            return await asyncio.to_thread(self._process_rnnoise, samples, None)
        except Exception:
            logger.exception("Denoise utterance processing failed; passthrough utterance")
            return samples

    async def health_check(self) -> bool:
        if not self._enabled:
            return True
        return self._ready

    def _init_rnnoise(self) -> None:
        import rnnoise
        self._model = rnnoise.RNNoise()
        logger.info("RNNoise model initialized")

    def _process_rnnoise(self, samples: np.ndarray, state=None) -> np.ndarray:
        """
        RNNoise attend du PCM int16 mono 48kHz, frames de 480 samples.
        On resample 16k→48k, on traite par frames, on resample 48k→16k.
        """
        from scipy.signal import resample_poly

        # 16k → 48k
        audio_48k = resample_poly(samples, 3, 1).astype(np.float32)

        # float32 → int16
        pcm_int16 = (audio_48k * 32767).clip(-32768, 32767).astype(np.int16)

        frame_size = 480
        out_frames = []

        for i in range(0, len(pcm_int16) - frame_size + 1, frame_size):
            frame = pcm_int16[i:i + frame_size]
            denoised = self._model.process_frame(frame, state)
            out_frames.append(denoised)

        if not out_frames:
            return samples

        out_int16 = np.concatenate(out_frames)
        out_float = (out_int16.astype(np.float32) / 32767.0)

        # 48k → 16k
        out_16k = resample_poly(out_float, 1, 3).astype(np.float32)

        # Ajuster la taille à l'original
        target_len = len(samples)
        if len(out_16k) >= target_len:
            return np.clip(out_16k[:target_len], -1.0, 1.0)
        else:
            padded = np.zeros(target_len, dtype=np.float32)
            padded[:len(out_16k)] = out_16k
            return padded