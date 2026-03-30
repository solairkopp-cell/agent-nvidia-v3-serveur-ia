"""
services/kokoro_tts_service.py
Synthèse vocale via Kokoro ONNX (local, no network).

Responsabilité :
  - Charger le modèle Kokoro ONNX une fois au démarrage
  - Découper le texte entrant en phrases (splitter)
  - Synthétiser chaque phrase et yielder les samples numpy
  - Gérer le look-ahead (synthèse N+1 pendant livraison de N)
  - Appliquer un fade-out lors d'une interruption

Protégé par asyncio.Lock : une seule synthèse à la fois
(le modèle ONNX n'est pas thread-safe).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import numpy as np

import config
from services.tts_utils import extract_tts_ready_segments


class KokoroTTSService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._kokoro = None         # kokoro_onnx.Kokoro chargé dans startup()
        self._lock = asyncio.Lock() # protège le modèle ONNX
        self._voice: str = config.KOKORO_VOICE
        self._lang: str = config.KOKORO_LANG
        self._speed: float = config.KOKORO_SPEED
        self._device: str = getattr(config, "KOKORO_DEVICE", "cpu")

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger Kokoro depuis config.KOKORO_MODEL_PATH et KOKORO_VOICES_PATH.
        Le chargement est bloquant → exécuter dans asyncio.to_thread().
        Logger la durée de chargement.
        """
        logger = logging.getLogger(__name__)

        model_path = Path(config.KOKORO_MODEL_PATH)
        voices_path = Path(config.KOKORO_VOICES_PATH)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Kokoro model not found at '{model_path}'. "
                "Set KOKORO_MODEL_PATH to the .onnx file path."
            )
        if not voices_path.exists():
            raise FileNotFoundError(
                f"Kokoro voices not found at '{voices_path}'. "
                "Set KOKORO_VOICES_PATH to the voices .bin file path."
            )

        # Sur certaines configs Jetson, l'init GPU peut provoquer des erreurs NvMap.
        # Forcer CPU en masquant les devices CUDA.
        if self._device.lower().strip() == "cpu":
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

        def _load():
            from kokoro_onnx import Kokoro  # type: ignore
            import onnxruntime as ort

            providers = ["CPUExecutionProvider"]
            available = ort.get_available_providers()
            # Sur Orin Nano 8GB, CUDA est préférable à TensorRT pour éviter les pics de RAM au démarrage
            if "CUDAExecutionProvider" in available:
                providers.insert(0, "CUDAExecutionProvider")
            if "TensorrtExecutionProvider" in available:
                providers.append("TensorrtExecutionProvider")

            return Kokoro(
                model_path=str(model_path),
                voices_path=str(voices_path),
            )

        start = time.perf_counter()
        self._kokoro = await asyncio.to_thread(_load)
        logger.info("Kokoro loaded in %.2fs", time.perf_counter() - start)

    async def shutdown(self):
        """Libérer les ressources."""
        self._kokoro = None

    # ── Synthèse ─────────────────────────────────────────────────────────────

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """
        Synthétiser un texte complet.
        Retourne (samples float32, sample_rate).
        Protégé par self._lock.
        Exécuté dans asyncio.to_thread() pour ne pas bloquer la boucle.
        """
        if self._kokoro is None:
            raise RuntimeError("KokoroTTSService not started (startup() not called).")

        text = (text or "").strip()
        if not text:
            return np.array([], dtype=np.float32), config.SAMPLE_RATE

        async with self._lock:
            kokoro = self._kokoro

            def _do():
                samples, rate = kokoro.create(
                    text=text,
                    voice=self._voice,
                    speed=self._speed,
                    lang=self._lang,
                )
                # kokoro_onnx retourne float32
                if not isinstance(samples, np.ndarray):
                    samples = np.asarray(samples, dtype=np.float32)
                return samples.astype(np.float32, copy=False), int(rate)

            return await asyncio.to_thread(_do)

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        cancel_check: Optional[callable] = None,
    ) -> AsyncIterator[tuple[str, np.ndarray, int]]:
        """
        Mode streaming : consomme les tokens LLM au fur et à mesure.

        Algorithme :
          1. Accumuler les tokens dans un buffer
          2. Dès qu'une ponctuation est détectée → extraire la phrase
          3. Synthétiser la phrase (look-ahead : lancer N+1 pendant livraison de N)
          4. Yield (phrase_text, samples, sample_rate)
          5. Si cancel_check() → synthétiser fade-out des 3 premiers mots et stopper

        Yield : (phrase_text, audio_samples, sample_rate)
        """
        buffer = ""
        # Look-ahead logic: synthesis N+1 while delivering N
        queue: asyncio.Queue[Optional[tuple[str, np.ndarray, int]]] = asyncio.Queue(maxsize=3)
        loop = asyncio.get_running_loop()

        async def _synthesizer():
            nonlocal buffer
            try:
                # 1. Consommer le flux de texte
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

                # 2. Flush du reste
                if not (cancel_check is not None and cancel_check()):
                    ready_segments, _ = extract_tts_ready_segments(buffer, final=True)
                    for phrase in ready_segments:
                        samples, rate = await self.synthesize(phrase)
                        await queue.put((phrase, samples, rate))
            except Exception as e:
                logging.getLogger(__name__).exception("TTS Stream Synthesizer error")
            finally:
                # Gestion du fade-out en cas d'annulation
                if cancel_check is not None and cancel_check():
                    fade_text = buffer.strip()
                    if fade_text:
                        samples, rate = await self.synthesize_fade_out(fade_text)
                        await queue.put((fade_text, samples, rate))
                
                await queue.put(None) # Sentinel

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
            with suppress(asyncio.CancelledError):
                await synth_task

    async def synthesize_fade_out(self, text: str, duration_ms: int = 150) -> tuple[np.ndarray, int]:
        """
        Synthétiser les 3 premiers mots avec fade-out exponentiel.
        Utilisé lors d'une interruption pour une coupure naturelle.
        """
        words = (text or "").strip().split()
        short = " ".join(words[:3]).strip()
        if not short:
            short = "..."
        samples, rate = await self.synthesize(short)
        return self.apply_fade_out(samples, rate, duration_ms=duration_ms), rate

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def apply_fade_out(self, samples: np.ndarray, rate: int, duration_ms: int = 200) -> np.ndarray:
        """
        Appliquer un fade-out exponentiel sur les N derniers ms.
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32, copy=False)
        if samples.size == 0:
            return samples

        n = int(rate * (duration_ms / 1000.0))
        n = max(1, min(n, samples.shape[0]))

        fade = np.exp(np.linspace(0.0, -6.0, num=n, dtype=np.float32))
        out = samples.copy()
        out[-n:] *= fade
        return out

    async def health_check(self) -> bool:
        """
        Synthétiser une courte phrase de test.
        Retourne True si ça fonctionne.
        """
        try:
            samples, rate = await self.synthesize("test.")
            return isinstance(samples, np.ndarray) and samples.size > 0 and isinstance(rate, int) and rate > 0
        except Exception:
            return False


