"""
services/agent_service.py
Orchestration centrale du pipeline IA : STT → LLM → TTS.

Responsabilité :
  - Recevoir un utterance complet (WAV bytes) depuis WebRTCService
  - Orchestrer STT → LLM (streaming) → TTS (streaming)
  - Alimenter le TTSAudioTrack de la session en temps réel
  - Gérer l'annulation si une nouvelle utterance arrive pendant le traitement
  - Mettre à jour l'historique de conversation dans la Session

Flux principal :
  wav_bytes → WhisperService.transcribe()
            → OllamaService.generate_stream()
            → KokoroTTSService.synthesize_stream()
            → Session.tts_track.feed(samples)

Le lock session.processing_lock garantit qu'un seul pipeline
s'exécute par session à la fois.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.session import Session
    from services.whisper_service import WhisperService
    from services.ollama_service import OllamaService
    from services.kokoro_tts_service import KokoroTTSService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService


class AgentService:
    """
    Singleton. Injecté dans WebRTCService.
    """

    def __init__(
        self,
        stt: "WhisperService",
        llm: "OllamaService",
        tts: "KokoroTTSService",
        audio: "AudioService",
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio = audio
        # Référence optionnelle au WebSocketService pour envoyer
        # des événements texte au client (transcript, réponse LLM)
        self.ws_service: "WebSocketService | None" = None

    # ── Pipeline principal ────────────────────────────────────────────────────

    async def process_utterance(self, session: "Session", wav_bytes: bytes) -> None:
        """
        Point d'entrée principal. Appelé par WebRTCService après
        détection de fin d'utterance par le VAD.

        Étapes :
          1. Acquérir session.processing_lock (annuler si déjà en cours)
          2. Incrémenter session.current_request_id
          3. STT : WhisperService.transcribe(wav_bytes)
          4. Si transcript vide → relâcher le lock et retourner
          5. Notifier le client du transcript via WebSocketService (optionnel)
          6. Ajouter {"role":"user","content":transcript} à session.conversation_history
          7. LLM streaming → TTS streaming (voir _stream_response)
          8. Ajouter {"role":"assistant","content":full_reply} à l'historique
          9. session.trim_history(MAX_HISTORY, TRIM_TO)

        Gestion de l'annulation :
          Si session.cancel_flag est True à n'importe quelle étape → stopper.
          cancel_flag est mis à True par interrupt() avant de relancer process_utterance.
        """
        raise NotImplementedError

    async def interrupt(self, session: "Session") -> None:
        """
        Annuler le traitement en cours pour cette session.
        
        Actions :
          1. session.cancel_flag = True
          2. Vider la queue du TTSAudioTrack si il existe
          3. Notifier le client via WebSocket {"type": "interrupted"}
        
        Appelé par WebRTCService quand une nouvelle utterance est détectée
        pendant qu'une réponse TTS est en cours de diffusion.
        """
        raise NotImplementedError

    # ── Pipeline interne ─────────────────────────────────────────────────────

    async def _stream_response(
        self,
        session: "Session",
        user_text: str,
        request_id: int,
    ) -> str:
        """
        LLM streaming → TTS streaming → TTSAudioTrack.

        Algorithme :
          1. Créer un token_stream = OllamaService.generate_stream(user_text, history)
          2. Passer token_stream à KokoroTTSService.synthesize_stream(
               token_stream,
               cancel_check=lambda: session.cancel_flag or session.current_request_id != request_id
             )
          3. Pour chaque (phrase, samples, rate) yielded :
               - Vérifier cancel_flag + request_id
               - audio_service.array_to_av_frame(samples, rate)
               - session.tts_track.feed(av_frame)
               - Optionnel : notifier le client du texte via WebSocket
          4. Retourner le texte complet généré

        Retourne le texte complet (pour l'historique).
        """
        raise NotImplementedError

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive pour éviter la dépendance circulaire."""
        self.ws_service = ws_service
