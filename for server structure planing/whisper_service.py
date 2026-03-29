"""
services/whisper_service.py
Client HTTP vers le service Whisper (faster-whisper sur :8080).

Responsabilité :
  - Envoyer du WAV bytes via multipart POST à /inference
  - Parser la réponse JSON (text + detected_language)
  - Gérer les timeouts et les erreurs réseau

Le service Whisper tourne comme processus séparé (voir whisper_server.py).
Ce client ne connaît pas le modèle utilisé côté serveur.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import config


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None      # langue détectée par Whisper
    duration_ms: Optional[float] = None # durée du traitement


class WhisperService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._url: str = config.WHISPER_URL
        self._timeout: int = config.WHISPER_TIMEOUT
        # Client HTTP async (httpx.AsyncClient) initialisé dans startup()
        self._client = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Créer le client HTTP async (httpx.AsyncClient avec pool de connexions).
        Vérifier que le serveur Whisper est joignable (health check).
        """
        raise NotImplementedError

    async def shutdown(self):
        """Fermer le client HTTP proprement."""
        raise NotImplementedError

    # ── Transcription ─────────────────────────────────────────────────────────

    async def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        """
        Envoyer wav_bytes en multipart POST à WHISPER_URL/inference.

        Payload :
          files={"file": ("audio.wav", wav_bytes, "audio/wav")}
          data={"response_format": "verbose_json", "language": config.WHISPER_LANGUAGE}

        Réponse attendue :
          {"text": "...", "language": "fr", "duration": 0.42}

        Gestion d'erreurs :
          - Timeout → retourner TranscriptionResult(text="")
          - HTTP 500 → logger + retourner TranscriptionResult(text="")
          - JSON malformé → idem
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """
        GET WHISPER_URL/ → retourne True si le service répond.
        Appelé au démarrage pour valider la configuration.
        """
        raise NotImplementedError
