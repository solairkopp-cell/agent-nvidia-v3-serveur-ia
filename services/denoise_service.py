"""
services/denoise_service.py
Débruitage du flux audio entrant avant VAD.

Backend principal :
  - RNNoise via `pyrnnoise`

Comportement :
  - Si le backend n'est pas disponible, le service devient un passthrough.
  - L'état de stream RNNoise est recréé par session/track.
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import TYPE_CHECKING
import warnings

import numpy as np

import config

if TYPE_CHECKING:
    from services.audio_service import AudioService


logger = logging.getLogger(__name__)


class DenoiseService:
    def __init__(self, audio: "AudioService"):
        self.audio = audio
        self._enabled: bool = bool(getattr(config, "DENOISE_ENABLED", False))
        self._backend: str = str(getattr(config, "DENOISE_BACKEND", "rnnoise")).strip().lower()
        self._stream_sample_rate: int = int(config.SAMPLE_RATE)

        self._ready: bool = False
        self._rnnoise_cls = None

    async def startup(self) -> None:
        if not self._enabled:
            logger.info("Denoise disabled")
            return
        if self._backend != "rnnoise":
            logger.warning("Unsupported denoise backend '%s'; passthrough mode", self._backend)
            return

        try:
            await asyncio.to_thread(self._startup_rnnoise)
            self._ready = True
            logger.info(
                "Denoise backend ready backend=%s stream_sr=%d",
                self._backend,
                self._stream_sample_rate,
            )
        except Exception:
            self._ready = False
            logger.exception("Denoise startup failed; passthrough mode enabled")

    async def shutdown(self) -> None:
        self._ready = False
        self._rnnoise_cls = None
        await asyncio.to_thread(self._cleanup_resources)

    def create_stream_state(self):
        if not self._ready or self._rnnoise_cls is None:
            return None
        return self._rnnoise_cls(self._stream_sample_rate)

    def release_stream_state(self, state) -> None:
        if state is None:
            return
        try:
            reset = getattr(state, "reset", None)
            if callable(reset):
                reset()
        except Exception:
            logger.debug("Failed to reset denoise stream state", exc_info=True)

    async def process(self, samples: np.ndarray, *, sample_rate: int, state=None) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples

        if not self._enabled or not self._ready or state is None:
            return samples

        try:
            return await asyncio.to_thread(
                self._process_rnnoise,
                samples,
                int(sample_rate),
                state,
            )
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
            return await asyncio.to_thread(
                self._process_rnnoise_utterance,
                samples,
                int(sample_rate),
            )
        except Exception:
            logger.exception("Denoise utterance processing failed; passthrough utterance")
            return samples

    async def health_check(self) -> bool:
        if not self._enabled:
            return True
        return self._ready

    def _startup_rnnoise(self) -> None:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*TripleDES has been moved.*")
            from pyrnnoise import RNNoise  # type: ignore

        probe = RNNoise(self._stream_sample_rate)
        probe.reset()
        self._rnnoise_cls = RNNoise

    def _process_rnnoise(self, samples: np.ndarray, sample_rate: int, state, *, partial: bool = False) -> np.ndarray:
        if sample_rate != self._stream_sample_rate:
            logger.debug(
                "Unexpected denoise sample rate=%d expected=%d; passthrough current chunk",
                sample_rate,
                self._stream_sample_rate,
            )
            return samples

        chunks: list[np.ndarray] = []
        for _speech_prob, frame in state.denoise_chunk(samples, partial=partial):
            arr = np.asarray(frame)
            if arr.size == 0:
                continue
            arr = arr.reshape(-1)
            if np.issubdtype(arr.dtype, np.integer):
                arr = arr.astype(np.float32, copy=False) / 32768.0
            else:
                arr = arr.astype(np.float32, copy=False)
            chunks.append(arr)

        if not chunks:
            return np.array([], dtype=np.float32)
        return np.clip(np.concatenate(chunks), -1.0, 1.0).astype(np.float32, copy=False)

    def _process_rnnoise_utterance(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        state = self.create_stream_state()
        if state is None:
            return samples
        try:
            out = self._process_rnnoise(samples, sample_rate, state, partial=True)
            if out.size == 0:
                return samples
            return out
        finally:
            self.release_stream_state(state)

    def _cleanup_resources(self) -> None:
        gc.collect()
