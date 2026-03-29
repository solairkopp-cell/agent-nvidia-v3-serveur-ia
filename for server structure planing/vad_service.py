"""
services/vad_service.py
Voice Activity Detection via Silero VAD (ONNX).

Responsabilité :
  - Charger le modèle Silero une seule fois au démarrage
  - Scorer chaque chunk audio (32ms)
  - Décider si on est en phase de parole ou de silence
  - Signaler la fin d'utterance quand le silence est suffisamment long

NB : le modèle ONNX est partagé entre toutes les sessions.
     L'état VAD (buffer, compteurs) est dans Session, pas ici.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

import config
from models.session import Session


@dataclass
class VADResult:
    """Résultat du traitement d'un chunk par le VAD."""
    type: str           # "speech_start" | "speech" | "silence" | "utterance_end"
    speech_prob: float  # score Silero brut (0.0 → 1.0)
    audio: Optional[np.ndarray] = None  # rempli uniquement si type == "utterance_end"


class VADService:
    """
    Singleton. Chargé une fois dans main.py et injecté dans WebRTCService.
    """

    def __init__(self):
        self._model = None  # SileroVadOnnx (chargé dans startup())
        self._chunk_samples: int = 0   # calculé depuis config.VAD_CHUNK_MS
        self._silence_threshold: int = 0  # nb chunks silence → utterance_end
        self._min_speech_chunks: int = 0  # nb chunks min pour valider utterance

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger le modèle Silero ONNX depuis config.SILERO_MODEL_PATH.
        Calculer les seuils en chunks depuis les constantes ms.
        Appelé une fois au démarrage de l'application (lifespan FastAPI).
        """
        raise NotImplementedError

    async def shutdown(self):
        """Libérer les ressources ONNX."""
        raise NotImplementedError

    # ── Traitement par session ────────────────────────────────────────────────

    def process_chunk(self, session: Session, chunk: np.ndarray) -> VADResult:
        """
        Traite un chunk de config.VAD_CHUNK_MS ms pour une session donnée.

        Lit et met à jour l'état VAD dans session :
          session.is_speaking
          session.silence_chunks
          session.speech_chunks
          session.audio_buffer

        Retourne un VADResult :
          - "speech_start"   : début de parole détecté
          - "speech"         : parole en cours
          - "silence"        : silence (pas encore assez long)
          - "utterance_end"  : fin d'utterance → audio contient le buffer complet

        Règles :
          speech_prob > config.VAD_SILENCE_THRESHOLD → speech
          silence_chunks >= _silence_threshold ET speech_chunks >= _min_speech_chunks → utterance_end
          utterance trop courte → réinitialiser le buffer sans déclencher STT
        """
        raise NotImplementedError

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def score(self, chunk: np.ndarray) -> float:
        """
        Appel direct au modèle Silero.
        Retourne la probabilité de présence vocale (0.0 → 1.0).
        Le chunk doit faire exactement self._chunk_samples samples @ 16kHz.
        """
        raise NotImplementedError

    def pad_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """
        Pad ou tronque le chunk à la taille exacte attendue par Silero.
        """
        raise NotImplementedError
