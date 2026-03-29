"""
services/audio_service.py
Utilitaires bas niveau : resampling, conversion format, encodage.
Pas d'état — toutes les fonctions sont pures ou stateless.
"""
from __future__ import annotations

import io
import numpy as np
import soundfile as sf


# ── Constantes ────────────────────────────────────────────────────────────────
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1          # mono


class AudioService:
    """
    Conversions et transformations audio.
    S'instancie une seule fois (singleton via DI dans main.py).
    """

    # ── Conversion format ────────────────────────────────────────────────────

    def pcm_bytes_to_array(self, raw: bytes, dtype: str = "float32") -> np.ndarray:
        """
        Bytes PCM bruts → numpy array float32.
        Utilisé pour les frames WebRTC (av.AudioFrame.to_ndarray).
        """
        raise NotImplementedError

    def array_to_wav_bytes(self, samples: np.ndarray, rate: int = TARGET_SAMPLE_RATE) -> bytes:
        """
        numpy float32 → WAV bytes (io.BytesIO).
        Utilisé pour envoyer l'audio au service Whisper.
        """
        raise NotImplementedError

    def wav_bytes_to_array(self, wav_bytes: bytes) -> tuple[np.ndarray, int]:
        """
        WAV bytes → (numpy float32, sample_rate).
        Utilisé pour lire la réponse audio de Kokoro.
        """
        raise NotImplementedError

    def array_to_av_frame(self, samples: np.ndarray, sample_rate: int):
        """
        numpy float32 → av.AudioFrame prêt pour aiortc.
        Format : s16, layout mono, pts calculé.
        """
        raise NotImplementedError

    # ── Resampling ───────────────────────────────────────────────────────────

    def resample(
        self,
        samples: np.ndarray,
        source_rate: int,
        target_rate: int = TARGET_SAMPLE_RATE,
    ) -> np.ndarray:
        """
        Resampling linéaire léger.
        source_rate → target_rate (typiquement 48000 → 16000).
        """
        raise NotImplementedError

    # ── Normalisation ────────────────────────────────────────────────────────

    def to_mono(self, samples: np.ndarray) -> np.ndarray:
        """
        Stéréo ou multi-canal → mono (moyenne des canaux).
        """
        raise NotImplementedError

    def normalize(self, samples: np.ndarray) -> np.ndarray:
        """
        Normalise le volume (peak normalization à 0.95).
        Évite le clipping.
        """
        raise NotImplementedError

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def concat(self, chunks: list[np.ndarray]) -> np.ndarray:
        """
        Concatène une liste de numpy arrays en un seul.
        Utilisé pour assembler le buffer VAD en utterance complet.
        """
        raise NotImplementedError

    def duration_ms(self, samples: np.ndarray, rate: int = TARGET_SAMPLE_RATE) -> float:
        """
        Durée en millisecondes d'un array audio.
        """
        raise NotImplementedError
