"""
services/piper_tts_service.py
Synthèse vocale via Piper binaire compilé.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np
import soxr

import config
from services.tts_utils import extract_tts_ready_segments


class PiperTTSService:

    def __init__(self):
        self._lock = asyncio.Lock()
        self._model_path = config.PIPER_MODEL_PATH
        self._config_path = config.PIPER_CONFIG_PATH
        self._piper_bin = config.PIPER_BIN_PATH  # ex: /home/server/piper/piper/piper
        self._sample_rate = 22050

    async def startup(self):
        logger = logging.getLogger(__name__)
        model_path = Path(self._model_path)
        config_path = Path(self._config_path)
        piper_bin = Path(self._piper_bin)

        if not piper_bin.exists():
            raise FileNotFoundError(f"Piper binary not found at '{piper_bin}'")
        if not model_path.exists():
            raise FileNotFoundError(f"Piper model not found at '{model_path}'")
        if not config_path.exists():
            raise FileNotFoundError(f"Piper config not found at '{config_path}'")

        with open(config_path, 'r') as f:
            cfg = json.load(f)
            self._sample_rate = cfg.get("audio", {}).get("sample_rate", 22050)

        logger.info("Piper binary ready bin=%s sample_rate=%d", self._piper_bin, self._sample_rate)

    async def shutdown(self):
        pass

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        target_rate = 48000
        text = (text or "").strip()
        if not text:
            return np.array([], dtype=np.float32), target_rate

        async with self._lock:
            def _do():
                proc = subprocess.run(
                    [
                        self._piper_bin,
                        "--model", self._model_path,
                        "--config", self._config_path,
                        "--output-raw",
                    ],
                    input=text.encode("utf-8"),
                    capture_output=True,
                )
                if proc.returncode != 0:
                    raise RuntimeError(f"Piper error: {proc.stderr.decode()}")

                samples = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
                samples_48k = soxr.resample(samples, self._sample_rate, target_rate)
                return samples_48k.astype(np.float32), target_rate

            return await asyncio.to_thread(_do)

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        cancel_check: Optional[callable] = None,
    ) -> AsyncIterator[tuple[str, np.ndarray, int]]:
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
                logging.getLogger(__name__).exception("Piper TTS Stream Synthesizer error")
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