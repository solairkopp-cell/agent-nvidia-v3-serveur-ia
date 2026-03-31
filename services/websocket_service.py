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
  {"type": "test_tts", "text": "..."}        → lire un texte via le TTS sans micro

Protocole de signaling (serveur → client) :
  {"type": "answer",     "sdp": "..."}
  {"type": "ice",        "candidate": {...}}
  {"type": "transcript", "text": "..."}      → texte STT reçu
  {"type": "response",   "text": "..."}      → fragment de réponse LLM
  {"type": "tts_test",   "text": "..."}      → fragment de texte joué par le test TTS
  {"type": "tts_stop_now"}                   → couper immédiatement la lecture côté client
  {"type": "interruption_decision", ...}     → décision continuation / interruption
  {"type": "interrupted"}                    → TTS interrompu
  {"type": "error",      "message": "..."}
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from models.session import Session

if TYPE_CHECKING:
    from services.webrtc_service import WebRTCService
    from services.notification_service import NotificationService


logger = logging.getLogger(__name__)


class WebSocketService:
    """
    Singleton. Injecté dans les routes FastAPI (main.py).
    """

    def __init__(
        self,
        webrtc: "WebRTCService",
        notification: "NotificationService | None" = None,
    ):
        self.webrtc = webrtc
        self.notification = notification
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
        await websocket.accept()
        client_id = str(uuid.uuid4())
        session = Session(client_id=client_id, websocket=websocket)
        self._sessions[client_id] = session
        logger.info("WS connected client_id=%s", client_id)
        return session

    async def disconnect(self, session: Session) -> None:
        """
        Nettoyer proprement à la déconnexion.
        Actions :
          1. Supprimer de self._sessions
          2. webrtc.cleanup(session)
          3. Logger la déconnexion
        """
        self._sessions.pop(session.client_id, None)
        try:
            await self.webrtc.cleanup(session)
        except Exception:
            logger.exception("Error during WebRTC cleanup client_id=%s", session.client_id)
        logger.info("WS disconnected client_id=%s", session.client_id)

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
        try:
            while True:
                try:
                    message = await session.websocket.receive()
                except RuntimeError as e:
                    # Client déconnecté immédiatement après connexion
                    logger.debug("Receive failed (client disconnected) client_id=%s: %s", session.client_id, e)
                    break

                # Ignorer les messages binaires ou de contrôle
                if message.get("type") not in ("websocket.receive", "websocket.connect"):
                    continue

                # Parser le JSON manuellement
                text = message.get("text")
                if not text:
                    continue

                try:
                    import json
                    data = json.loads(text)
                except (json.JSONDecodeError, ValueError):
                    await self.send_error(session, "invalid JSON")
                    continue

                if not isinstance(data, dict):
                    await self.send_error(session, "invalid message")
                    continue

                await self.handle_message(session, data)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("WS listen error client_id=%s", session.client_id)
        finally:
            await self.disconnect(session)

    async def handle_message(self, session: Session, message: dict) -> None:
        """
        Router un message entrant selon son type.

        "offer"  → sdp = webrtc.handle_offer(session, message["sdp"])
                    send(session, {"type": "answer", "sdp": sdp})

        "ice"    → webrtc.add_ice_candidate(session, message["candidate"])

        "start"  → logger + éventuellement créer le peer à l'avance

        "stop"   → webrtc.cleanup(session)

        Types notification → notification.on_message(session, message)

        Inconnu → send(session, {"type": "error", "message": "unknown type"})
        """
        msg_type = message.get("type")
        
        # Log tous les messages reçus
        logger.info("📨 WS MESSAGE RECEIVED client_id=%s type=%s data=%r", 
                    session.client_id, msg_type, message)

        # Notification : laisser le notification_service traiter en premier
        if self.notification is not None:
            await self.notification.on_message(session, message)
        if msg_type == "offer":
            sdp = message.get("sdp")
            if not isinstance(sdp, str) or not sdp.strip():
                await self.send_error(session, "missing sdp")
                return
            try:
                answer_sdp = await self.webrtc.handle_offer(session, sdp)
            except Exception as exc:
                logger.exception("handle_offer failed client_id=%s", session.client_id)
                await self.send_error(session, f"offer failed: {exc}")
                return
            await self.send(session, {"type": "answer", "sdp": answer_sdp})
            return

        if msg_type == "ice":
            candidate = message.get("candidate")
            if candidate is None:
                # end-of-candidates support
                return
            if not isinstance(candidate, dict):
                await self.send_error(session, "invalid candidate")
                return
            try:
                await self.webrtc.add_ice_candidate(session, candidate)
            except Exception as exc:
                logger.exception("add_ice_candidate failed client_id=%s", session.client_id)
                await self.send_error(session, f"ice failed: {exc}")
            return

        if msg_type == "start":
            # Optionnel : pré-créer le peer côté serveur avant offer.
            if session.peer is None:
                try:
                    await self.webrtc.create_peer(session)
                except Exception as exc:
                    logger.exception("create_peer failed client_id=%s", session.client_id)
                    await self.send_error(session, f"start failed: {exc}")
                    return
            await self.send(session, {"type": "started"})
            return

        if msg_type == "stop":
            await self.webrtc.cleanup(session)
            await self.send(session, {"type": "stopped"})
            return

        if msg_type == "arrived":
            # Message direct: {"type": "arrived", "id": "trip_id"}
            trip_id = message.get("id") or message.get("trip_id")
            if not trip_id:
                await self.send_error(session, "missing arrived trip id")
                return
            asyncio.create_task(
                self.webrtc.agent.handle_external_control(
                    session, "arrived", {"trip_id": trip_id}
                )
            )
            return

        if msg_type == "test_tts":
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                await self.send_error(session, "missing test tts text")
                return
            if session.tts_track is None:
                await self.send_error(session, "tts not ready: start webrtc first")
                return
            asyncio.create_task(self.webrtc.agent.speak_text(session, text))
            return

        if msg_type == "external_control":
            # Recevoir des événements de contrôle externe du client
            # Ex: {"type": "external_control", "action": "arrived", "extras": {"trip_id": "..."}}
            action = message.get("action")
            extras = message.get("extras", {})
            if not action:
                await self.send_error(session, "missing external_control action")
                return
            asyncio.create_task(
                self.webrtc.agent.handle_external_control(session, action, extras)
            )
            return

        await self.send_error(session, "unknown type")

    # ── Envoi ─────────────────────────────────────────────────────────────────

    async def send(self, session: Session, data: dict) -> None:
        """
        Envoyer un message JSON au client de cette session.
        Ignorer silencieusement si la connexion est fermée.
        """
        try:
            logger.debug("📤 WS MESSAGE SENT client_id=%s type=%s data=%r", 
                        session.client_id, data.get("type"), data)
            await session.websocket.send_json(data)
        except Exception:
            # La connexion peut être fermée / en erreur.
            return

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

    @property
    def active_webrtc_peers(self) -> int:
        """
        Nombre de sessions ayant un RTCPeerConnection actif.
        """
        return sum(1 for s in self._sessions.values() if getattr(s, "peer", None) is not None)

    async def health_check(self) -> bool:
        """
        Health check local: le serveur WS est "up" si ce service est instancié.
        """
        return True
