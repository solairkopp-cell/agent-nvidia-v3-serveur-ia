"""
services/delivery_service.py
Service de gestion des livraisons pour l'agent vocal.

Responsabilité :
  - Identifier un driver par son numéro de série
  - Récupérer les trips (livraisons) d'un driver
  - Envoyer les trips au client via WebSocket
  - Mettre à jour le statut des packages
  - Gérer les échecs de livraison

Flux :
  Client → identify_driver → DeliveryService → PlanningService → Trips → Client
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
from pathlib import Path

if TYPE_CHECKING:
    from models.session import Session
    from services.websocket_service import WebSocketService
    from services.notification_service import NotificationService


logger = logging.getLogger(__name__)


class DeliveryService:
    """
    Singleton. Injecté avec NotificationService.
    Interface entre les messages WebSocket et le PlanningService.
    """

    def __init__(
        self,
        notification_service: "NotificationService | None" = None,
        ws_service: "WebSocketService | None" = None,
    ):
        self.notification_service = notification_service
        self.ws_service = ws_service
        self._planning_service = None
        self._driver_sessions: dict[str, str] = {}  # client_id -> driver_serial

    def set_notification_service(self, notification_service: "NotificationService") -> None:
        """Injection tardive de NotificationService."""
        self.notification_service = notification_service

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive de WebSocketService."""
        self.ws_service = ws_service

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """
        Initialiser le service au démarrage.
        """
        logger.info("DeliveryService started")

    async def shutdown(self) -> None:
        """
        Nettoyage à l'arrêt.
        """
        if self._planning_service is not None:
            try:
                await self._planning_service.close()
            except Exception:
                pass
        self._driver_sessions.clear()
        logger.info("DeliveryService shutdown")

    # ── Identification Driver ────────────────────────────────────────────────

    async def identify_driver(self, session: Session, message: dict) -> None:
        """
        Identifier un driver et récupérer ses livraisons.

        Args:
            session: Session du client
            message: Message WebSocket contenant driver_serial
        """
        # Extraire le driver_serial du message
        driver_serial = message.get("driver_serial", "").strip()

        if not driver_serial:
            logger.warning("Missing driver_serial in identify_driver message client_id=%s", session.client_id)
            await self._send_error_notification(session, "driver_serial manquant")
            return

        logger.info(
            "🚚 Identifying driver client_id=%s serial=%s",
            session.client_id,
            driver_serial,
        )

        # Sauvegarder l'association client_id -> driver_serial
        self._driver_sessions[session.client_id] = driver_serial

        # Stocker dans la session pour la machine à états
        session.driver_serial = driver_serial

        # Récupérer les trips et le nom du driver
        try:
            trips, driver_name = await self._get_trips(driver_serial)

            if trips:
                logger.info("✅ Found %d trips for driver %s (%s)", len(trips), driver_name, driver_serial)

                # Envoyer les trips au client
                await self._send_trips_to_client(session, trips)

                # Stocker les infos pour le résumé vocal (à envoyer après ouverture du flux audio)
                session._pending_voice_summary = {
                    "trips": trips,
                    "driver_name": driver_name,
                }

                # Si le flux audio est déjà prêt, envoyer le résumé vocal immédiatement
                if session.tts_track is not None:
                    await self._send_voice_summary(session, trips, driver_name)
            else:
                logger.info("ℹ️ No trips found for driver %s", driver_serial)
                await self._send_no_trips_notification(session, driver_name)

        except Exception as e:
            logger.exception("❌ Error identifying driver client_id=%s: %s", session.client_id, e)
            await self._send_error_notification(session, f"Erreur lors de l'identification: {e}")

    async def _get_trips(self, driver_serial_number: str) -> tuple:
        """
        Récupérer les trips d'un driver via PlanningService.

        Returns:
            Tuple (trips, driver_name) où:
            - trips: Liste de Trip objects
            - driver_name: Nom du driver (ex: "Vivien")
        """
        # Import dynamique pour éviter les dépendances circulaires
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "data_base_service"))

        try:
            from service.planning_service import PlanningService
            from service import TokenManager
            from service.logger_service import log_error

            # Créer un nouveau PlanningService pour cette requête
            script_dir = Path(__file__).parent.parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)

            try:
                # Utiliser la méthode get_delivery_trips avec le bon paramètre
                # date et output_file sont automatiques
                trips = await planning_service.get_delivery_trips(
                    driver_serial_number=driver_serial_number,
                    date=None,  # Date du jour (automatique)
                    export_json=True,
                    output_file="data.json",  # Nom fixe
                )
                
                # Récupérer le nom du driver
                driver_name = await self._get_driver_name(driver_serial_number)
                
                return trips, driver_name
            finally:
                await planning_service.close()

        except ImportError as e:
            logger.error("Failed to import PlanningService: %s", e)
            return [], "Driver"
        except Exception as e:
            logger.error("Error getting trips: %s", e)
            try:
                log_error(f"DeliveryService error: {e}")
            except Exception:
                pass
            return [], "Driver"

    async def _get_driver_name(self, driver_serial_number: str) -> str:
        """
        Récupérer le nom du driver par son numéro de série.
        """
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "data_base_service"))

        try:
            from service.planning_service import PlanningService
            from service import TokenManager

            script_dir = Path(__file__).parent.parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)

            try:
                await planning_service._init_services()
                driver = await planning_service._crud.search_driver(driver_serial_number)
                if driver and driver.name:
                    return driver.name
                return "Driver"
            finally:
                await planning_service.close()

        except Exception as e:
            logger.debug("Error getting driver name: %s", e)
            return "Driver"

    async def _send_trips_to_client(self, session: Session, trips: list) -> None:
        """
        Envoyer la liste des trips au client via WebSocket.

        Format :
        {
            "type": "notification",
            "notification_type": "trips_list",
            "data": {
                "driver_serial": "...",
                "trip_count": N,
                "trips": [
                    {
                        "id": "...",
                        "name": "...",
                        "client_name": "...",
                        "address": "...",
                        "latitude": ...,
                        "longitude": ...,
                        "status": "...",
                        "package_info": "..."
                    },
                    ...
                ]
            }
        }
        """
        if self.notification_service is None:
            logger.warning("NotificationService not set, cannot send trips")
            return

        trips_data = []
        for trip in trips:
            # Trip object from planning_service has methods like get_id(), get_name(), etc.
            trip_dict = {
                "id": getattr(trip, 'id', None) or getattr(trip, 'get_id', lambda: None)(),
                "name": getattr(trip, 'name', None) or getattr(trip, 'get_name', lambda: None)(),
                "latitude": getattr(trip, 'latitude', None) or getattr(trip, 'get_latitude', lambda: None)(),
                "longitude": getattr(trip, 'longitude', None) or getattr(trip, 'get_longitude', lambda: None)(),
                "clientName": getattr(trip, 'client_name', None) or getattr(trip, 'get_client_name', lambda: None)(),
                "packageInfo": getattr(trip, 'package_info', None) or getattr(trip, 'get_package_info', lambda: None)(),
                "deliveryStatus": getattr(trip, 'status', None) or getattr(trip, 'get_delivery_status', lambda: None)(),
                "isFragile": "Fragile" in (getattr(trip, 'package_info', None) or getattr(trip, 'get_package_info', lambda: "")() or ""),
            }
            trips_data.append(trip_dict)

        await self.notification_service.send(
            session=session,
            notification_type="trips_list",
            data={
                "driver_serial": self._driver_sessions.get(session.client_id, ""),
                "trip_count": len(trips),
                "trips": trips_data,
            },
        )

    async def _send_voice_summary(self, session: Session, trips: list, driver_name: str = "Driver") -> None:
        """
        Envoyer un résumé vocal des livraisons.

        Message TTS : "Hello {driver_name}, you have {X} trips. The first one is a {package_info} for {client_name}. Have a great day."
        """
        if self.ws_service is None:
            return

        trip_count = len(trips)

        # Récupérer les infos du premier trip
        first_trip = trips[0] if trips else None
        client_name = None
        package_info = None

        if first_trip:
            client_name = getattr(first_trip, 'client_name', None) or getattr(first_trip, 'get_client_name', lambda: None)()
            package_info = getattr(first_trip, 'package_info', None) or getattr(first_trip, 'get_package_info', lambda: None)()

        # Construire le message vocal
        if first_trip and client_name and package_info:
            summary_text = (
                f"Hello {driver_name}, you have {trip_count} trips. "
                f"The first one is a {package_info} for {client_name}. "
                f"Have a great day."
            )
        elif first_trip and client_name:
            summary_text = (
                f"Hello {driver_name}, you have {trip_count} trips. "
                f"The first one is for {client_name}. "
                f"Have a great day."
            )
        else:
            summary_text = f"Hello {driver_name}, you have {trip_count} trips. Have a great day."

        # Envoyer l'émotion greeting avant le message vocal
        try:
            await self.ws_service.send(session, {"type": "emotion", "name": "greeting"})
            logger.info("😊 Emotion greeting sent client_id=%s", session.client_id)
        except Exception as e:
            logger.error("Could not send emotion greeting: %s", e)

        # Utiliser speak_text de AgentService pour parler directement
        try:
            if self.ws_service is not None and self.ws_service.audio_stream is not None:
                agent = self.ws_service.audio_stream.agent
                await agent.speak_instruction(
                    session,
                    instruction=(
                        "You are a delivery assistant greeting the driver. "
                        f"Driver name: {driver_name}. Number of trips: {trip_count}. "
                        f"First trip client: {client_name or 'unknown'}. "
                        f"First trip package info: {package_info or 'not specified'}. "
                        "Produce one friendly welcome sentence."
                    ),
                    fallback=summary_text,
                )
                logger.info("🔊 Voice summary sent: %s", summary_text)
        except Exception as e:
            logger.debug("Could not send voice summary: %s", e)

    async def _send_no_trips_notification(self, session: Session, driver_name: str = "Driver") -> None:
        """
        Envoyer une notification quand aucun trip n'est trouvé.
        """
        if self.notification_service is None:
            return

        voice_message = f"Hello {driver_name}, you have no trips scheduled for today. Have a great day."

        await self.notification_service.send(
            session=session,
            notification_type="no_trips",
            data={
                "message": "Aucune livraison prévue pour aujourd'hui",
                "voice_message": voice_message,
            },
        )

        # Stocker le message vocal en attente (à envoyer après ouverture du flux audio)
        session._pending_voice_summary = {
            "trips": [],
            "driver_name": driver_name,
            "no_trips": True,
            "voice_message": voice_message,
        }

        # Si le flux audio est déjà prêt, envoyer le message vocal immédiatement
        if session.tts_track is not None:
            # Envoyer l'émotion greeting avant le message vocal
            try:
                if self.ws_service is not None:
                    await self.ws_service.send(session, {"type": "emotion", "name": "greeting"})
                    logger.info("😊 Emotion greeting sent client_id=%s", session.client_id)
            except Exception as e:
                logger.error("Could not send emotion greeting: %s", e)

            try:
                if self.ws_service is not None and self.ws_service.audio_stream is not None:
                    agent = self.ws_service.audio_stream.agent
                    await agent.speak_instruction(
                        session,
                        instruction=(
                            "You are a delivery assistant greeting the driver. "
                            f"Driver name: {driver_name}. "
                            "There are no trips scheduled today. "
                            "Produce one short friendly spoken message."
                        ),
                        fallback=voice_message,
                    )
                    logger.info("🔊 No trips voice message sent: %s", voice_message)
            except Exception as e:
                logger.error("Could not send no trips voice message: %s", e)

    async def _send_error_notification(self, session: Session, message: str) -> None:
        """
        Envoyer une notification d'erreur.
        """
        if self.notification_service is None:
            return

        await self.notification_service.send(
            session=session,
            notification_type="error",
            data={
                "message": message,
            },
        )

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def get_driver_serial(self, client_id: str) -> str | None:
        """
        Récupérer le numéro de série du driver pour une session.
        """
        return self._driver_sessions.get(client_id)

    def is_driver_identified(self, client_id: str) -> bool:
        """
        Vérifier si un driver est identifié.
        """
        return client_id in self._driver_sessions

    async def start_delivery_completion(
        self,
        session: Session,
        trip_id: Optional[str] = None,
    ) -> None:
        """
        Démarrer le flux de complétion de livraison (MODE_1).
        
        Args:
            session: Session courante
            trip_id: ID du trip à compléter (optionnel, prend le premier si None)
        """
        from services.main import state_machine  # Import depuis main.py
        
        if state_machine is None:
            logger.warning("State machine not available")
            return
        
        driver_serial = self.get_driver_serial(session.client_id)
        if not driver_serial:
            logger.warning(
                "Cannot start delivery completion: driver not identified client_id=%s",
                session.client_id,
            )
            return
        
        # Si trip_id non spécifié, récupérer le premier trip non complété
        if not trip_id:
            trips, _driver_name = await self._get_trips(driver_serial)
            for trip in trips:
                status = getattr(trip, 'status', None)
                if status != "COMPLETED":
                    trip_id = getattr(trip, 'id', None)
                    break
        
        if not trip_id:
            logger.warning(
                "No trip available for completion client_id=%s",
                session.client_id,
            )
            return
        
        # Stocker le trip_id dans la session
        session.current_trip_id = trip_id
        
        # Entrer dans MODE_1 → STATE_1
        await state_machine.enter_mode_1(session, trip_id)

        # Jouer la première question via le pipeline TTS serveur (Piper -> ws audio).
        tts_text = "Is the delivery completed?"
        played = False
        try:
            if self.ws_service is not None and self.ws_service.audio_stream is not None:
                agent = self.ws_service.audio_stream.agent
                await agent.speak_instruction(
                    session,
                    instruction=(
                        "Ask the driver a short yes/no question to confirm "
                        "whether the current delivery is completed."
                    ),
                    fallback=tts_text,
                )
                played = True
        except Exception:
            logger.exception(
                "Could not play delivery start TTS client_id=%s trip_id=%s",
                session.client_id,
                trip_id,
            )

        # Conserver la notification pour le front (telemetrie/UI), meme si l'audio a deja ete joue.
        if self.notification_service is not None:
            await self.notification_service.send(
                session=session,
                notification_type="state_machine_start",
                data={
                    "type": "tts_speak",
                    "text": tts_text,
                    "played_server_side": played,
                },
            )
        
        logger.info(
            "🚀 Delivery completion started client_id=%s trip_id=%s",
            session.client_id,
            trip_id,
        )

    async def _handle_get_trips_wrapper(self, session: Session, message: dict) -> None:
        """
        Wrapper pour handle_get_trips (méthode statique).
        """
        await handle_get_trips(session, message)

    async def health_check(self) -> bool:
        """
        Health check : True si le service est opérationnel.
        """
        return True


# ── Handlers prédéfinis ──────────────────────────────────────────────────────

async def handle_identify_driver(session: Session, message: dict) -> None:
    """
    Handler pour le message identify_driver.

    Message attendu :
    {
        "type": "identify_driver",
        "driver_serial": "000"
    }
    """
    from services.main import delivery_service  # Import depuis main.py

    driver_serial = message.get("driver_serial", "").strip()
    if not driver_serial:
        logger.warning("Missing driver_serial in identify_driver message")
        return

    await delivery_service.identify_driver(session, driver_serial)


async def handle_get_trips(session: Session, message: dict) -> None:
    """
    Handler pour le message get_trips (rafraîchir les livraisons).

    Message attendu :
    {
        "type": "get_trips"
    }
    """
    from services.main import delivery_service  # Import depuis main.py

    driver_serial = delivery_service.get_driver_serial(session.client_id)
    if not driver_serial:
        logger.warning("Driver not identified, cannot get trips")
        await delivery_service._send_error_notification(
            session, "Driver non identifié. Envoyez d'abord identify_driver."
        )
        return

    await delivery_service.identify_driver(session, driver_serial)
