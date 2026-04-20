"""
services/websocket_service.py
Gestion du transport WebSocket.

Responsabilité :
  - Accepter les connexions WebSocket
  - Maintenir le registre des sessions actives
  - Router les messages JSON et binaires vers le pipeline audio
  - Envoyer des événements au client (transcript, réponse LLM, erreurs)

Protocole JSON (client → serveur) :
  {"type": "start", "input_sample_rate": 48000}  → initialiser la session audio
  {"type": "stop"}                               → cleanup()
  {"type": "test_tts", "text": "..."}            → lire un texte via le TTS sans micro

Protocole binaire (client → serveur) :
  bytes PCM16 mono                               → micro entrant

Protocole JSON (serveur → client) :
  {"type": "started", "audio_output_sample_rate": 48000, ...}
  {"type": "transcript", "text": "..."}      → texte STT reçu
  {"type": "response",   "text": "..."}      → fragment de réponse LLM
  {"type": "tts_test",   "text": "..."}      → fragment de texte joué par le test TTS
  {"type": "tts_stop_now"}                   → couper immédiatement la lecture côté client
  {"type": "interruption_decision", ...}     → décision continuation / interruption
  {"type": "interrupted"}                    → TTS interrompu
  {"type": "error",      "message": "..."}

Protocole binaire (serveur → client) :
  bytes PCM16 mono                               → chunks audio TTS
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from models.session import Session

if TYPE_CHECKING:
    from services.ws_audio_service import WebSocketAudioService
    from services.notification_service import NotificationService


logger = logging.getLogger(__name__)


class WebSocketService:
    """
    Singleton. Injecté dans les routes FastAPI (main.py).
    """

    def __init__(
        self,
        audio_stream: "WebSocketAudioService",
        notification: "NotificationService | None" = None,
    ):
        self.audio_stream = audio_stream
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
        
        # Démarrer une tâche de ping keep-alive (toutes les 10 secondes)
        session._ping_task = asyncio.create_task(self._ping_keepalive(session))
        
        logger.info("WS connected client_id=%s", client_id)
        return session

    async def _ping_keepalive(self, session: Session, interval: float = 10.0) -> None:
        """
        Envoyer un ping WebSocket périodique pour garder la connexion active.
        Utilise le ping natif WebSocket (pas un message JSON).
        """
        try:
            while True:
                await asyncio.sleep(interval)
                # Ping natif WebSocket (le client répond automatiquement avec un pong)
                await session.websocket.ping()
        except Exception:
            # Task annulée quand la session se déconnecte
            pass

    async def disconnect(self, session: Session) -> None:
        """
        Nettoyer proprement à la déconnexion.
        Actions :
          1. Annuler la tâche de ping
          2. Supprimer de self._sessions
          3. audio_stream.cleanup(session)
          4. Logger la déconnexion
        """
        # Annuler le ping keep-alive
        if session._ping_task is not None and not session._ping_task.done():
            session._ping_task.cancel()
            try:
                await session._ping_task
            except asyncio.CancelledError:
                pass
        
        self._sessions.pop(session.client_id, None)
        try:
            await self.audio_stream.cleanup(session)
        except Exception:
            logger.exception("Error during audio stream cleanup client_id=%s", session.client_id)
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

                if message.get("type") not in ("websocket.receive", "websocket.connect"):
                    continue

                audio_bytes = message.get("bytes")
                if audio_bytes:
                    await self.audio_stream.handle_audio_bytes(session, audio_bytes)
                    continue

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

        "start"  → initialiser la session audio WS

        "stop"   → audio_stream.cleanup(session)

        Types notification → notification.on_message(session, message)

        Inconnu → send(session, {"type": "error", "message": "unknown type"})
        """
        msg_type = message.get("type")
        
        # Log tous les messages reçus
        logger.info("📨 WS MESSAGE RECEIVED client_id=%s type=%s data=%r", 
                    session.client_id, msg_type, message)

        # Notification : laisser le notification_service traiter en premier
        handled_by_notification = False
        if self.notification is not None:
            handled_by_notification = await self.notification.on_message(session, message)
            if handled_by_notification:
                return

        if msg_type == "start":
            raw_rate = message.get("input_sample_rate")
            input_sample_rate = int(raw_rate) if isinstance(raw_rate, (int, float)) and int(raw_rate) > 0 else None
            try:
                await self.audio_stream.start_session(session, input_sample_rate=input_sample_rate)
            except Exception as exc:
                logger.exception("start audio session failed client_id=%s", session.client_id)
                await self.send_error(session, f"start failed: {exc}")
                return
            await self.send(
                session,
                {
                    "type": "started",
                    "input_sample_rate": session.audio_input_sample_rate,
                    "audio_output_sample_rate": session.audio_output_sample_rate,
                    "encoding": "pcm_s16le",
                    "channels": 1,
                },
            )
            asyncio.create_task(self.audio_stream.on_session_ready(session))
            return

        if msg_type == "stop":
            await self.audio_stream.cleanup(session)
            await self.send(session, {"type": "stopped"})
            return

        if msg_type == "arrived":
            # Message direct: {"type": "arrived", "id": "trip_id"}
            trip_id = message.get("id") or message.get("trip_id")
            if not trip_id:
                await self.send_error(session, "missing arrived trip id")
                return
            asyncio.create_task(
                self.audio_stream.agent.handle_external_control(
                    session, "arrived", {"trip_id": trip_id}
                )
            )
            return

        if msg_type == "photo_taken":
            # Réponse à ask_photo_event : photo prise avec succès
            asyncio.create_task(
                self.audio_stream.agent.handle_external_control(
                    session, "photo_taken", message
                )
            )
            return

        if msg_type == "photo_not_taken":
            # Réponse à ask_photo_event : photo non prise
            asyncio.create_task(
                self.audio_stream.agent.handle_external_control(
                    session, "photo_not_taken", message
                )
            )
            return

        if msg_type == "test_tts":
            text = message.get("text")
            if not isinstance(text, str) or not text.strip():
                await self.send_error(session, "missing test tts text")
                return
            if session.tts_track is None:
                await self.send_error(session, "tts not ready: send start first")
                return
            asyncio.create_task(self.audio_stream.agent.speak_text(session, text))
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
                self.audio_stream.agent.handle_external_control(session, action, extras)
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
            # Log tous les envois (y compris émotions)
            logger.info("📤 WS MESSAGE SENT client_id=%s type=%s data=%r",
                        session.client_id, data.get("type"), data)
            async with session.send_lock:
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
    def active_audio_streams(self) -> int:
        return sum(1 for s in self._sessions.values() if getattr(s, "audio_stream_started", False))

    async def health_check(self) -> bool:
        """
        Health check local: le serveur WS est "up" si ce service est instancié.
        """
        return True
