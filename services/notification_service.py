"""
services/notification_service.py
Service de notifications en temps réel via WebSocket.

Responsabilité :
  - Écouter les messages entrants des clients (via WebSocketService)
  - Permettre l'envoi de notifications aux clients connectés
  - Gérer un système d'abonnement/écoute pour les notifications
  - Interface avec les services externes (ex: planning_service)

Flux :
  1. Client → WebSocket → NotificationService.on_message() → traitement
  2. Service externe → NotificationService.send() → WebSocket → Client
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable, Awaitable

if TYPE_CHECKING:
    from models.session import Session
    from services.websocket_service import WebSocketService


logger = logging.getLogger(__name__)


class NotificationService:
    """
    Singleton. Injecté avec WebSocketService.
    S'abonne aux messages WebSocket et peut envoyer des notifications.
    """

    def __init__(self, ws_service: "WebSocketService | None" = None):
        self.ws_service = ws_service
        # Registre des handlers de messages par type
        self._message_handlers: dict[str, Callable[[Session, dict], Awaitable[None]]] = {}
        # Registre des listeners de notifications (pour services externes)
        self._notification_listeners: list[Callable[[str, dict], Awaitable[None]]] = []
        self._running = False
        self._listen_task: asyncio.Task | None = None

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive de WebSocketService (évite dépendance circulaire)."""
        self.ws_service = ws_service

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """
        Démarrer l'écoute des notifications.
        """
        self._running = True
        logger.info("NotificationService started")

    async def shutdown(self) -> None:
        """
        Arrêter l'écoute et nettoyer.
        """
        self._running = False
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        logger.info("NotificationService shutdown")

    # ── Enregistrement des handlers ──────────────────────────────────────────

    def register_handler(
        self,
        message_type: str,
        handler: Callable[[Session, dict], Awaitable[None]],
    ) -> None:
        """
        Enregistrer un handler pour un type de message.

        Exemple :
            notification_service.register_handler("client_location", handle_location)
        """
        self._message_handlers[message_type] = handler
        logger.info("Handler registered for message type: %s", message_type)

    def unregister_handler(self, message_type: str) -> None:
        """Supprimer un handler."""
        self._message_handlers.pop(message_type, None)

    # ── Réception des messages ───────────────────────────────────────────────

    async def on_message(self, session: Session, message: dict) -> bool:
        """
        Appelé par WebSocketService quand un message arrive.
        Route le message vers le handler approprié.

        Args:
            session: Session du client
            message: Message JSON reçu
        """
        msg_type = message.get("type")
        if not msg_type:
            return False

        # Log tous les messages reçus
        logger.info("📨 NOTIFICATION RECEIVED client_id=%s type=%s data=%r", 
                    session.client_id, msg_type, message)

        handler = self._message_handlers.get(msg_type)
        if handler:
            try:
                await handler(session, message)
            except Exception:
                logger.exception("Notification handler error client_id=%s type=%s", session.client_id, msg_type)
            return True
        else:
            # Pas de handler → message ignoré (pas d'erreur)
            logger.debug("No handler for message type %s client_id=%s", msg_type, session.client_id)
            return False

    # ── Envoi de notifications ───────────────────────────────────────────────

    async def send(
        self,
        session: Session,
        notification_type: str,
        data: dict | None = None,
    ) -> None:
        """
        Envoyer une notification à une session spécifique.

        Args:
            session: Session cible
            notification_type: Type de notification (ex: "new_delivery")
            data: Données de la notification

        Format envoyé :
            {"type": "notification", "notification_type": "...", "data": {...}}
        """
        if self.ws_service is None:
            logger.warning("WebSocketService not set, cannot send notification")
            return

        payload = {
            "type": "notification",
            "notification_type": notification_type,
            "data": data or {},
        }
        
        logger.info("📤 NOTIFICATION SENT client_id=%s type=%s data=%r", 
                    session.client_id, notification_type, data)
        await self.ws_service.send(session, payload)

    async def broadcast(
        self,
        notification_type: str,
        data: dict | None = None,
        exclude_client_id: str | None = None,
    ) -> None:
        """
        Envoyer une notification à tous les clients connectés.

        Args:
            notification_type: Type de notification
            data: Données de la notification
            exclude_client_id: ID du client à exclure (optionnel)
        """
        if self.ws_service is None:
            logger.warning("WebSocketService not set, cannot broadcast notification")
            return

        payload = {
            "type": "notification",
            "notification_type": notification_type,
            "data": data or {},
        }

        sessions = self.ws_service._sessions
        sent_count = 0
        for session in sessions.values():
            if exclude_client_id and session.client_id == exclude_client_id:
                continue
            try:
                await self.ws_service.send(session, payload)
                sent_count += 1
            except Exception:
                logger.debug("Failed to broadcast to client_id=%s", session.client_id)

        logger.info("📤 NOTIFICATION BROADCAST type=%s count=%d", notification_type, sent_count)

    async def send_to_client(
        self,
        client_id: str,
        notification_type: str,
        data: dict | None = None,
    ) -> bool:
        """
        Envoyer une notification à un client spécifique par son ID.

        Args:
            client_id: ID du client cible
            notification_type: Type de notification
            data: Données de la notification

        Returns:
            True si la notification a été envoyée, False si client non trouvé
        """
        if self.ws_service is None:
            return False

        session = self.ws_service.get_session(client_id)
        if session is None:
            logger.warning("Client not found: %s", client_id)
            return False

        logger.info("📤 NOTIFICATION SENT TO CLIENT client_id=%s type=%s data=%r", 
                    client_id, notification_type, data)
        await self.send(session, notification_type, data)
        return True

    # ── Listeners pour services externes ─────────────────────────────────────

    def add_notification_listener(
        self,
        listener: Callable[[str, dict], Awaitable[None]],
    ) -> None:
        """
        Ajouter un listener qui sera notifié de toutes les notifications envoyées.
        Utile pour les services externes qui veulent écouter en temps réel.

        Args:
            listener: Fonction async(notification_type, data)
        """
        self._notification_listeners.append(listener)
        logger.info("Notification listener added")

    def remove_notification_listener(
        self,
        listener: Callable[[str, dict], Awaitable[None]],
    ) -> None:
        """Supprimer un listener."""
        if listener in self._notification_listeners:
            self._notification_listeners.remove(listener)

    async def _notify_listeners(self, notification_type: str, data: dict) -> None:
        """Notifier tous les listeners."""
        for listener in self._notification_listeners:
            try:
                await listener(notification_type, data)
            except Exception:
                logger.exception("Notification listener error")

    # ── Utilitaires ──────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """
        Health check : True si le service est opérationnel.
        """
        return self._running

    def get_registered_handlers(self) -> list[str]:
        """Retourne la liste des types de messages enregistrés."""
        return list(self._message_handlers.keys())


# ── Exemples de handlers prédéfinis ──────────────────────────────────────────

async def handle_client_location(session: Session, message: dict) -> None:
    """
    Exemple de handler : recevoir la localisation du client.
    Message attendu : {"type": "client_location", "latitude": ..., "longitude": ...}
    """
    logger.info(
        "Client location received client_id=%s lat=%s lng=%s",
        session.client_id,
        message.get("latitude"),
        message.get("longitude"),
    )
    # Ici tu peux sauvegarder la position, notifier un service de tracking, etc.


async def handle_delivery_update(session: Session, message: dict) -> None:
    """
    Exemple de handler : recevoir une mise à jour de livraison.
    Message attendu : {"type": "delivery_update", "package_id": "...", "status": "..."}
    """
    logger.info(
        "Delivery update received client_id=%s package=%s status=%s",
        session.client_id,
        message.get("package_id"),
        message.get("status"),
    )
    # Ici tu peux appeler planning_service.update_package_status()
