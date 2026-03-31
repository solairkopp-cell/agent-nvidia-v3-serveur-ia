"""
services/kokoro_tts_service.py
Synthèse vocale via Kokoro-82M ONNX (CPU, lightweight).
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np
import config
from services.tts_utils import extract_tts_ready_segments


class KokoroTTSService:
    """
    Singleton. Injecté dans AgentService.
    Utilise Kokoro-82M via kokoro-onnx (CPU optimized).
    """

    def __init__(self):
        self._kokoro = None       # kokoro_onnx.Kokoro loaded in startup()
        self._lock = asyncio.Lock()  # protects the model
        self._model_path = config.KOKORO_MODEL_PATH
        self._voices_path = config.KOKORO_VOICES_PATH
        self._voice = config.KOKORO_VOICE  # default: "af_sarah"
        self._language = config.KOKORO_LANGUAGE  # default: "en-us"
        self._speed = config.KOKORO_SPEED  # default: 1.0
        self._sample_rate = 24000   # Kokoro output sample rate

    async def startup(self):
        """
        Charger Kokoro depuis les fichiers ONNX.
        """
        logger = logging.getLogger(__name__)
        model_path = Path(self._model_path)
        voices_path = Path(self._voices_path)

        if not model_path.exists():
            raise FileNotFoundError(f"Kokoro model not found at '{model_path}'")
        if not voices_path.exists():
            raise FileNotFoundError(f"Kokoro voices not found at '{voices_path}'")

        def _load():
            from kokoro_onnx import Kokoro
            return Kokoro(str(model_path), str(voices_path))

        start = time.perf_counter()
        self._kokoro = await asyncio.to_thread(_load)

        logger.info(
            "Kokoro loaded in %.2fs (voice=%s, lang=%s, speed=%.1f, sample_rate=%d)",
            time.perf_counter() - start,
            self._voice,
            self._language,
            self._speed,
            self._sample_rate,
        )

    async def shutdown(self):
        self._kokoro = None

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """
        Synthétiser un texte complet.
        Retourne (samples float32, sample_rate).
        """
        if self._kokoro is None:
            raise RuntimeError("KokoroTTSService not started")

        text = (text or "").strip()
        if not text:
            return np.array([], dtype=np.float32), self._sample_rate

        async with self._lock:
            def _do():
                # Kokoro outputs (samples: np.ndarray, sample_rate: int)
                samples, rate = self._kokoro.create(
                    text,
                    voice=self._voice,
                    speed=self._speed,
                    lang=self._language,
                )
                # Convert to float32 normalized [-1, 1]
                if samples.dtype == np.int16:
                    samples = samples.astype(np.float32) / 32768.0
                elif samples.dtype != np.float32:
                    samples = samples.astype(np.float32)
                return samples, rate

            return await asyncio.to_thread(_do)

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        cancel_check: Optional[callable] = None,
    ) -> AsyncIterator[tuple[str, np.ndarray, int]]:
        """
        Mode streaming : consomme les tokens LLM au fur et à mesure.
        Segmentation sur frontières naturelles.
        """
        buffer = ""
        queue: asyncio.Queue[Optional[tuple[str, np.ndarray, int]]] = asyncio.Queue(maxsize=3)

        async def _synthesizer():
            nonlocal buffer
            try:
                async for token in text_stream:
                    if cancel_check is not None and cancel_check():
                        break
                    if not token:
                        continue
                    buffer += token

                    ready_segments, buffer = extract_tts_ready_segments(buffer, final=False)
                    for phrase in ready_segments:
                        if cancel_check is not None and cancel_check():
                            break
                        samples, rate = await self.synthesize(phrase)
                        await queue.put((phrase, samples, rate))

                if not (cancel_check is not None and cancel_check()):
                    ready_segments, _ = extract_tts_ready_segments(buffer, final=True)
                    for phrase in ready_segments:
                        samples, rate = await self.synthesize(phrase)
                        await queue.put((phrase, samples, rate))
            except Exception:
                logging.getLogger(__name__).exception("Kokoro TTS Stream Synthesizer error")
            finally:
                if cancel_check is not None and cancel_check():
                    fade_text = buffer.strip()
                    if fade_text:
                        samples, rate = await self.synthesize_fade_out(fade_text)
                        await queue.put((fade_text, samples, rate))

                await queue.put(None)

        synth_task = asyncio.create_task(_synthesizer())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if not synth_task.done():
                synth_task.cancel()
            try:
                await synth_task
            except asyncio.CancelledError:
                pass

    async def synthesize_fade_out(self, text: str, duration_ms: int = 150) -> tuple[np.ndarray, int]:
        words = (text or "").strip().split()
        short = " ".join(words[:3]).strip()
        if not short:
            short = "..."
        samples, rate = await self.synthesize(short)
        return self.apply_fade_out(samples, rate, duration_ms=duration_ms), rate

    def apply_fade_out(self, samples: np.ndarray, rate: int, duration_ms: int = 200) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            return samples

        n = int(rate * (duration_ms / 1000.0))
        n = max(1, min(n, samples.shape[0]))

        fade = np.exp(np.linspace(0.0, -6.0, num=n, dtype=np.float32))
        out = samples.copy()
        out[-n:] *= fade
        return out

    async def health_check(self) -> bool:
        try:
            samples, rate = await self.synthesize("test.")
            return isinstance(samples, np.ndarray) and samples.size > 0
        except Exception:
            return False
