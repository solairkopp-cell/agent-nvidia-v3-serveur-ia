"""
services/websocket_service.py
Gestion du signaling WebSocket.

Responsabilité :
  - Accepter les connexions WebSocket
  - Maintenir le registre des sessions actives
  - Router les messages entrants vers WebRTCService
  - Envoyer des événements au client (transcript, réponse LLM, erreurs)

Protocole de signaling (client → serveur) :
  {"type": "offer",  "sdp": "..."}          → WebRTCService.handle_offer()
  {"type": "ice",    "candidate": {...}}     → WebRTCService.add_ice_candidate()
  {"type": "start"}                          → WebRTCService.create_peer() si besoin
  {"type": "stop"}                           → cleanup()

Protocole de signaling (serveur → client) :
  {"type": "answer",     "sdp": "..."}
  {"type": "ice",        "candidate": {...}}
  {"type": "transcript", "text": "..."}      → texte STT reçu
  {"type": "response",   "text": "..."}      → fragment de réponse LLM
  {"type": "interrupted"}                    → TTS interrompu
  {"type": "error",      "message": "..."}
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from models.session import Session

if TYPE_CHECKING:
    from services.webrtc_service import WebRTCService


class WebSocketService:
    """
    Singleton. Injecté dans les routes FastAPI (main.py).
    """

    def __init__(self, webrtc: "WebRTCService"):
        self.webrtc = webrtc
        # Registre de toutes les sessions actives
        self._sessions: dict[str, Session] = {}

    # ── Connexion ─────────────────────────────────────────────────────────────

    async def connect(self, websocket: WebSocket) -> Session:
        """
        Accepter la connexion WebSocket.
        Créer une Session avec un client_id unique (UUID4).
        Enregistrer dans self._sessions.
        Retourner la session créée.
        """
        raise NotImplementedError

    async def disconnect(self, session: Session) -> None:
        """
        Nettoyer proprement à la déconnexion.
        Actions :
          1. Supprimer de self._sessions
          2. webrtc.cleanup(session)
          3. Logger la déconnexion
        """
        raise NotImplementedError

    # ── Boucle de messages ────────────────────────────────────────────────────

    async def listen(self, session: Session) -> None:
        """
        Boucle principale de réception des messages WebSocket.
        Appelée depuis la route FastAPI après connect().

        while True:
            data = await session.websocket.receive_json()
            await handle_message(session, data)

        Capturer WebSocketDisconnect → appeler disconnect(session).
        Capturer toute autre exception → logger + disconnect(session).
        """
        raise NotImplementedError

    async def handle_message(self, session: Session, message: dict) -> None:
        """
        Router un message entrant selon son type.

        "offer"  → sdp = webrtc.handle_offer(session, message["sdp"])
                    send(session, {"type": "answer", "sdp": sdp})

        "ice"    → webrtc.add_ice_candidate(session, message["candidate"])

        "start"  → logger + éventuellement créer le peer à l'avance

        "stop"   → webrtc.cleanup(session)

        Inconnu → send(session, {"type": "error", "message": "unknown type"})
        """
        raise NotImplementedError

    # ── Envoi ─────────────────────────────────────────────────────────────────

    async def send(self, session: Session, data: dict) -> None:
        """
        Envoyer un message JSON au client de cette session.
        Ignorer silencieusement si la connexion est fermée.
        """
        raise NotImplementedError

    async def send_transcript(self, session: Session, text: str) -> None:
        """Raccourci : envoyer le transcript STT au client."""
        await self.send(session, {"type": "transcript", "text": text})

    async def send_response_chunk(self, session: Session, text: str) -> None:
        """Raccourci : envoyer un fragment de réponse LLM au client."""
        await self.send(session, {"type": "response", "text": text})

    async def send_error(self, session: Session, message: str) -> None:
        """Raccourci : envoyer une erreur au client."""
        await self.send(session, {"type": "error", "message": message})

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def get_session(self, client_id: str) -> Session | None:
        return self._sessions.get(client_id)

    @property
    def active_sessions(self) -> int:
        return len(self._sessions)
