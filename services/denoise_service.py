"""
services/denoise_service.py
Débruitage du flux audio entrant avant VAD.

Backend principal :
  - DeepFilterNet (plus performant que RNNoise)

Comportement :
  - Si le backend n'est pas disponible, le service devient un passthrough.
  - DeepFilterNet tourne nativement à 48kHz, resampling automatique 16k↔48k.
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import TYPE_CHECKING

import numpy as np
import torch

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
        self._df_state = None

    async def startup(self) -> None:
        if not self._enabled:
            logger.info("Denoise disabled")
            return

        try:
            await asyncio.to_thread(self._init_deepfilternet)
            self._ready = True
            logger.info(
                "Denoise backend ready backend=deepfilternet stream_sr=%d",
                self._stream_sample_rate,
            )
        except Exception:
            self._ready = False
            logger.exception("Denoise startup failed; passthrough mode enabled")

    async def shutdown(self) -> None:
        self._ready = False
        self._model = None
        self._df_state = None
        await asyncio.to_thread(self._cleanup_resources)

    def create_stream_state(self):
        # DeepFilterNet n'a pas d'état par stream comme RNNoise
        # On retourne un placeholder pour garder l'API compatible
        if not self._ready:
            return None
        return {}

    def release_stream_state(self, state) -> None:
        pass  # No-op pour DeepFilterNet

    async def process(self, samples: np.ndarray, *, sample_rate: int, state=None) -> np.ndarray:
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples

        if not self._enabled or not self._ready:
            return samples

        try:
            return await asyncio.to_thread(
                self._process_deepfilternet,
                samples,
                int(sample_rate),
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
                self._process_deepfilternet_utterance,
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

    def _init_deepfilternet(self) -> None:
        """Initialise le modèle DeepFilterNet2 (optimisé pour embarqué/temps réel)."""
        from df import init_df
        # DeepFilterNet2 est optimisé pour les appareils embarqués avec ~20ms de latence
        self._model, self._df_state, _ = init_df(default_model='DeepFilterNet2')
        logger.info("DeepFilterNet2 model initialized (embedded/real-time optimized)")

    def _process_deepfilternet(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Débruite un chunk audio avec DeepFilterNet.
        
        DeepFilterNet attend du 48kHz, donc on resample 16k→48k→16k.
        
        Args:
            samples: float32 numpy array [T] mono 16kHz
            sample_rate: fréquence d'échantillonnage des samples
        
        Returns:
            float32 numpy array [T] denoised
        """
        from df import enhance
        from scipy.signal import resample_poly
        
        if sample_rate != self._stream_sample_rate:
            logger.debug(
                "Unexpected sample rate=%d expected=%d; passthrough current chunk",
                sample_rate,
                self._stream_sample_rate,
            )
            return samples
        
        if self._model is None or self._df_state is None:
            return samples
        
        # Resample 16k→48k (DeepFilterNet native)
        audio_48k = resample_poly(samples, 3, 1).astype(np.float32)
        
        # [1, T] tensor pour torch
        tensor = torch.from_numpy(audio_48k).unsqueeze(0)
        
        # Denoise avec inference mode
        with torch.inference_mode():
            enhanced = enhance(self._model, self._df_state, tensor)
        
        # Resample 48k→16k
        enhanced_np = enhanced.squeeze(0).numpy()
        denoised_16k = resample_poly(enhanced_np, 1, 3).astype(np.float32)
        
        return np.clip(denoised_16k, -1.0, 1.0).astype(np.float32, copy=False)

    def _process_deepfilternet_utterance(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Débruite une utterance complète.
        Même logique que process() mais pour un traitement one-shot.
        """
        return self._process_deepfilternet(samples, sample_rate)

    def _cleanup_resources(self) -> None:
        """Nettoie les ressources torch."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._df_state is not None:
            del self._df_state
            self._df_state = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
