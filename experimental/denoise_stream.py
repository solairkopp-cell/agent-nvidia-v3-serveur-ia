"""
experimental/denoise_stream.py
Service de débruitage audio en temps réel via WebSocket.

Flux :
1. Client envoie des chunks audio (base64 PCM 16kHz)
2. Serveur traite avec DenoiseService / DeepFilterNet
3. Retourne l'audio débruité (base64 PCM)
"""
from __future__ import annotations

import base64
import logging

import numpy as np

from services.denoise_service import DenoiseService

logger = logging.getLogger(__name__)


class DenoiseStreamProcessor:
    """
    Processeur de débruitage en streaming pour une seule connexion WebSocket.

    Chaque instance garde son propre buffer et évite tout partage d'état
    entre plusieurs enregistrements / clients.
    """

    def __init__(self, denoise_service: DenoiseService, chunk_duration_ms: int = 100):
        self.denoise_service = denoise_service
        self.chunk_duration_ms = chunk_duration_ms
        self.sample_rate = 16000

        self._ready = False

        # Buffer d'accumulation pour lisser le flux entrant côté websocket
        self._audio_buffer: list[np.ndarray] = []
        self._total_samples = 0

        # Taille minimale pour traiter (100ms = 1600 samples à 16kHz)
        self.chunk_samples = int(self.sample_rate * chunk_duration_ms / 1000)

    def startup(self) -> bool:
        """
        Marque le processor comme prêt si le service de débruitage principal
        est disponible.
        """
        self._ready = bool(self.denoise_service and self.denoise_service._enabled and self.denoise_service._ready)

        if self._ready:
            logger.info("Denoise streaming processor ready")
        else:
            logger.warning("Denoise streaming processor unavailable; backend not ready")

        return self._ready

    def shutdown(self) -> None:
        """Libérer les ressources locales."""
        self._ready = False
        self._audio_buffer.clear()
        self._total_samples = 0

    def reset(self) -> None:
        """Reset le buffer pour un nouvel enregistrement."""
        self._audio_buffer.clear()
        self._total_samples = 0

    async def process_chunk(self, audio_base64: str) -> dict:
        """
        Traiter un chunk audio et retourner le résultat.

        Args:
            audio_base64: Chunk audio encodé en base64 (raw PCM 16-bit mono 16kHz)

        Returns:
            {
                "status": "ok|buffering|error",
                "audio": "<base64 denoised audio>",
                "buffered_ms": <ms accumulées>,
                "message": "..."
            }
        """
        if not self._ready:
            return {"status": "error", "message": "DenoiseProcessor not ready"}

        try:
            # Décoder le chunk
            audio_bytes = base64.b64decode(audio_base64)

            # Convertir en numpy array (raw PCM 16-bit mono 16kHz)
            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

            # Ajouter au buffer
            self._audio_buffer.append(samples)
            self._total_samples += len(samples)

            buffered_ms = int(self._total_samples / self.sample_rate * 1000)

            # Si on a assez d'audio pour traiter
            if self._total_samples >= self.chunk_samples:
                # Concaténer le buffer
                audio = np.concatenate(self._audio_buffer)

                # Traiter avec le service principal
                denoised = await self._denoise(audio)

                # Reset buffer
                self._audio_buffer.clear()
                self._total_samples = 0

                # Convertir en bytes
                denoised_bytes = self._float32_to_pcm16_bytes(denoised)
                denoised_base64 = base64.b64encode(denoised_bytes).decode()

                return {
                    "status": "ok",
                    "audio": denoised_base64,
                    "buffered_ms": 0,
                    "processed_ms": int(len(denoised) / self.sample_rate * 1000),
                }

            # Pas assez d'audio, on accumule
            return {
                "status": "buffering",
                "buffered_ms": buffered_ms,
                "message": f"Accumulating: {buffered_ms}ms / {self.chunk_duration_ms}ms",
            }

        except Exception as e:
            logger.error("Error processing chunk: %s", e, exc_info=True)
            return {"status": "error", "message": str(e)}

    async def process_final(self) -> dict:
        """
        Traiter le buffer restant (fin d'enregistrement).

        Returns:
            Audio débruité final
        """
        if not self._audio_buffer:
            return {"status": "ok", "audio": "", "message": "No buffered audio", "final": True}

        try:
            audio = np.concatenate(self._audio_buffer)
            denoised = await self._denoise(audio)

            self._audio_buffer.clear()
            self._total_samples = 0

            denoised_bytes = self._float32_to_pcm16_bytes(denoised)
            denoised_base64 = base64.b64encode(denoised_bytes).decode()

            return {
                "status": "ok",
                "audio": denoised_base64,
                "processed_ms": int(len(denoised) / self.sample_rate * 1000),
                "final": True,
            }

        except Exception as e:
            logger.error("Error in final processing: %s", e, exc_info=True)
            return {"status": "error", "message": str(e), "final": True}

    async def _denoise(self, samples: np.ndarray) -> np.ndarray:
        """
        Appliquer le DenoiseService principal sur un array numpy float32.
        """
        if len(samples) == 0:
            return samples

        denoised = await self.denoise_service.process(samples, sample_rate=self.sample_rate)
        return np.clip(np.asarray(denoised, dtype=np.float32), -1.0, 1.0)

    @staticmethod
    def _float32_to_pcm16_bytes(samples: np.ndarray) -> bytes:
        clipped = np.clip(samples, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)
        return pcm16.tobytes()


def create_denoise_stream_processor(denoise_service: DenoiseService) -> DenoiseStreamProcessor:
    """Créer un processor isolé pour une connexion WebSocket."""
    return DenoiseStreamProcessor(denoise_service=denoise_service)
