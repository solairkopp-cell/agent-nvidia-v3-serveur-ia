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

from services.utility_service import UtilityService

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
        session.awaiting_driver_serial = False
        session.auth_attempts = 0

        if self.ws_service is not None:
            await self.ws_service.send(
                session,
                {
                    "type": "auth",
                    "event": "driver_identified",
                    "driver_serial": driver_serial,
                },
            )

        # Récupérer les trips et le nom du driver
        try:
            istrue, driver_name, driver_exists, trips = await self._get_trips(driver_serial)
            if not driver_exists:
                # ── Driver introuvable en base : reset de l'auth et message d'erreur ──
                logger.warning(
                    "🚫 Driver not found, resetting auth client_id=%s serial=%s",
                    session.client_id, driver_serial,
                )
                # Réinitialiser la session pour permettre une nouvelle tentative
                session.driver_serial = None
                self._driver_sessions.pop(session.client_id, None)
                session.awaiting_driver_serial = True
                session.auth_mode = "voice_driver_serial"
                session.auth_attempts += 1

                if self.ws_service is not None:
                    await self.ws_service.send(
                        session,
                        {
                            "type": "auth",
                            "event": "driver_not_found",
                            "driver_serial": driver_serial,
                            "attempts": session.auth_attempts,
                        },
                    )
                    # Message vocal d'erreur + invitation à réessayer
                    await self._send_driver_not_found_tts(session, driver_serial)
                return

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

    async def _get_trips(self, driver_serial_number: str) -> tuple[bool, str, bool, list]:
        """
        Returns:
            Tuple (success, driver_name, driver_exists, trips)
            - trips: liste d'objets Trip (vide si echec)
        """

        try:
            from .data_base_service.service.planning_service import PlanningService, DriverNotFoundError
            from .data_base_service.service import TokenManager
            from .data_base_service.entities.models import Trip

            script_dir = Path(__file__).parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)

            try:
                success = await planning_service.get_delivery_trips(
                    driver_serial_number=driver_serial_number,
                    date=None,
                )

                # Reconstruire les objets Trip depuis le cache UtilityService
                # (get_delivery_trips() a déjà chargé les données dans UtilityService)
                trips: list = []
                if success:
                    raw_items = UtilityService().get_all_deliveries()  # liste de dicts
                    for item in raw_items:
                        try:
                            # Le cache stocke des dicts avec clé "address" (renommé depuis "name")
                            # On reconstruit un dict compatible avec Trip.from_dict()
                            trip_data = dict(item)
                            if "address" in trip_data and "name" not in trip_data:
                                trip_data["name"] = trip_data["address"]
                            trips.append(Trip.from_dict(trip_data))
                        except Exception as e_trip:
                            logger.warning("Could not reconstruct Trip from dict: %s – %s", item, e_trip)

                driver_name = await self._get_driver_name(driver_serial_number)
                return success, driver_name, True, trips

            except DriverNotFoundError:
                logger.warning("🚫 Driver not found in database: %s", driver_serial_number)
                return False, "Driver", False, []

            finally:
                await planning_service.close()

        except ImportError as e:
            logger.error("Failed to import PlanningService: %s", e)
            return False, "Driver", True, []
        except Exception as e:
            logger.error("Error getting trips: %s", e)
            return False, "Driver", True, []

    async def _get_driver_name(self, driver_serial_number: str) -> str:
        """
        Récupérer le nom du driver par son numéro de série.
        """


        try:
            from .data_base_service.service.planning_service import PlanningService
            from .data_base_service.service import TokenManager

            script_dir = Path(__file__).parent / "data_base_service"
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
            # Support Trip objects (dataclass) AND plain dicts (legacy)
            if isinstance(trip, dict):
                pkg_info = trip.get("packageInfo") or trip.get("package_info", "")
                trip_dict = {
                    "id": trip.get("id"),
                    "name": trip.get("name") or trip.get("address"),
                    "latitude": trip.get("latitude"),
                    "longitude": trip.get("longitude"),
                    "clientName": trip.get("clientName") or trip.get("client_name"),
                    "packageInfo": pkg_info,
                    "deliveryStatus": trip.get("deliveryStatus") or trip.get("delivery_status"),
                    "isFragile": "Fragile" in (pkg_info or ""),
                }
            else:
                # Trip dataclass object
                pkg_info = trip.package_info or ""
                trip_dict = {
                    "id": trip.id,
                    "name": trip.name,
                    "latitude": trip.latitude,
                    "longitude": trip.longitude,
                    "clientName": trip.client_name,
                    "packageInfo": trip.package_info,
                    "deliveryStatus": trip.delivery_status,
                    "isFragile": "Fragile" in pkg_info,
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

                # Extraire les infos du premier trip (Trip objet ou dict)
                first_trip = trips[0] if trips else None
                if isinstance(first_trip, dict):
                    first_pkg_info = first_trip.get("packageInfo") or first_trip.get("package_info") or "delivery"
                    first_client = first_trip.get("clientName") or first_trip.get("client_name") or "a client"
                elif first_trip is not None:
                    first_pkg_info = first_trip.package_info or "delivery"
                    first_client = first_trip.client_name or "a client"
                else:
                    first_pkg_info = "delivery"
                    first_client = "a client"

                await agent.speak_text(
                    session,
                    text=(
                        f"Hello {driver_name}, you have {len(trips)} trip{'s' if len(trips) > 1 else ''}. "
                        f"The first one is a {first_pkg_info} for {first_client}. "
                        "Have a great day."
                    ),
                )
        except Exception as e:
            logger.error("Could not send voice summary: %s", e)

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
                    await agent.speak_text(session, text=voice_message)
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

    async def _send_driver_not_found_tts(self, session: Session, driver_serial: str) -> None:
        """
        Jouer un message vocal indiquant que le numéro de driver n'existe pas,
        puis fermer la connexion WebSocket (le client devra se reconnecter).
        """
        tts_message = (
            f"Sorry, driver number {driver_serial} was not found. "
            "Please try again."
        )
        logger.info(
            "🚫 Driver not found TTS + closing WS client_id=%s serial=%s",
            session.client_id, driver_serial,
        )
        try:
            if self.ws_service is not None and self.ws_service.audio_stream is not None:
                agent = self.ws_service.audio_stream.agent
                await agent.speak_instruction(
                    session,
                    instruction=(
                        "You are a voice authentication system for delivery drivers. "
                        f"The driver said their number is {driver_serial}, but it was not found in the system. "
                        "Politely inform them and tell them to try again. "
                        "Keep it short and clear."
                    ),
                    fallback=tts_message,
                )
            elif self.ws_service is not None:
                await self.ws_service.send(
                    session,
                    {"type": "auth_prompt", "text": tts_message},
                )
        except Exception as e:
            logger.error("Could not send driver_not_found TTS: %s", e)
        finally:
            # Fermer la connexion WebSocket après le message vocal
            # Code 4401 = authentification échouée (custom code)
            logger.info(
                "🔌 Closing WS connection after driver not found client_id=%s",
                session.client_id,
            )
            try:
                import asyncio
                # Petite pause pour laisser le temps au TTS de terminer côté client
                await asyncio.sleep(0.5)
                await session.websocket.close(code=4401, reason="driver_not_found")
            except Exception as e:
                logger.debug("WS close error (already closed?) client_id=%s: %s", session.client_id, e)


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
            _success, _driver_name, _exists, trips = await self._get_trips(driver_serial)
            for trip in trips:
                # Support Trip objects (dataclass) AND plain dicts
                if isinstance(trip, dict):
                    status = trip.get("deliveryStatus") or trip.get("delivery_status")
                    trip_id = trip.get("id")
                else:
                    status = trip.delivery_status
                    trip_id = trip.id
                if status != "COMPLETED":
                    break
                trip_id = None  # reset if COMPLETED, continue loop
        
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
