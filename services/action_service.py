"""
services/action_service.py
Gestion des actions connues après la détection d'intention.

Responsabilité :
  - Recevoir l'intention détectée et la transcription
  - Si intention = "INCONNU" → retourner la transcription pour le LLM
  - Si intention = action connue (start_navigation, show_deliveries, etc.) → exécuter l'action localement
  - Ne PAS envoyer les actions connues au LLM (économie de ressources)
  - Envoyer des événements external_control au client pour les actions de navigation

Flux :
  transcription + intention → ActionService.execute()
    → Si INCONNU : retourne {"action": "forward_to_llm", "text": transcription}
    → Si action connue : exécute l'action, retourne {"action": "handled", "intent": "...", "response": "..."}
    → Envoie événement external_control au client via WebSocket
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.session import Session

import config


class ActionService:
    """
    Singleton. Injecté dans AgentService.
    Placé entre IntentService et LLM.
    """

    def __init__(self):
        self._known_intents = self._load_known_intents()
        self._logger = logging.getLogger(__name__)
        self._ws_service = None
        self._data_file = Path("data.json")
        self._start_navigation_in_progress_by_client: dict[str, bool] = {}

    def set_ws_service(self, ws_service) -> None:
        """Injection tardive de WebSocketService pour envoyer des événements."""
        self._ws_service = ws_service

    def _load_known_intents(self) -> tuple[str, ...]:
        """
        Charger la liste des intentions connues depuis config.
        """
        # Intentions connues qui ne doivent PAS être envoyées au LLM
        return getattr(config, "ACTION_KNOWN_INTENTS", (
            "start_navigation",
            "show_deliveries",
            "repeat_last_sentence",
            "get_next_client_name",
            "get_next_delivery_address",
            "get_possible_delivery_failure_reason",
            "stop_listening",
        ))

    async def execute(self, session: Session, intent: str, transcription: str) -> ActionResult:
        """
        Exécuter une action ou décider de l'envoyer au LLM.

        Args:
            session: Session courante
            intent: Intention détectée (ex: "start_navigation", "INCONNU")
            transcription: Texte transcrit par le STT

        Returns:
            ActionResult avec:
              - handled=True si l'action a été traitée localement
              - handled=False si la transcription doit être envoyée au LLM
              - response: Réponse textuelle à envoyer au TTS (si handled=True)
        """
        # Intent inconnu → envoyer au LLM
        if intent == "INCONNU":
            self._logger.info(
                "Intent INCONNU → forward to LLM client_id=%s text=%r",
                session.client_id,
                transcription[:50] if transcription else "",
            )
            return ActionResult(
                handled=False,
                intent=intent,
                text_to_llm=transcription,
                response=None,
            )

        # Action connue → exécuter localement
        if intent in self._known_intents:
            self._logger.info(
                "Intent connue [%s] → exécution locale client_id=%s",
                intent,
                session.client_id,
            )
            response = await self._handle_known_action(session, intent, transcription)
            return ActionResult(
                handled=True,
                intent=intent,
                text_to_llm=None,
                response=response,
            )

        # Intent non listée mais pas INCONNU → envoyer au LLM par défaut
        self._logger.info(
            "Intent [%s] non listée → forward to LLM client_id=%s",
            intent,
            session.client_id,
        )
        return ActionResult(
            handled=False,
            intent=intent,
            text_to_llm=transcription,
            response=None,
        )

    async def _handle_known_action(self, session: Session, intent: str, transcription: str) -> str:
        """
        Exécuter une action connue et retourner une réponse textuelle pour le TTS.

        Args:
            session: Session courante
            intent: Nom de l'intention (ex: "start_navigation")
            transcription: Texte original (peut servir pour le contexte)

        Returns:
            Réponse textuelle à synthétiser par le TTS
        """
        # Log l'intention pour débogage / action externe
        self._logger.info("ACTION: %s", intent)

        # Réponses par défaut pour chaque intention
        responses = {
            "start_navigation": "Starting navigation to the next destination.",
            "show_deliveries": "Here is the list of your deliveries.",
            "repeat_last_sentence":   (session.conversation_history[-1]["content"] if session.conversation_history else "nothing"),
            "get_possible_delivery_failure_reason": "Here are the possible reasons for delivery failure.",
            "stop_listening": "Disabling listening.",
        }

        # Gestion spécifique pour get_next_client_name
        if intent == "get_next_client_name":
            client_name = await self._get_next_client_name()
            if client_name:
                return f"Your next client is {client_name}."
            return "No client found."

        # Gestion spécifique pour get_next_delivery_address
        if intent == "get_next_delivery_address":
            address = await self._get_next_delivery_address()
            if address:
                return f"Your next delivery is at {address}."
            return "No delivery address found."

        response = responses.get(intent, f"Action {intent} exécutée.")

        # Envoyer un événement external_control pour start_navigation
        if intent == "start_navigation":
            client_id = session.client_id
            if not self._start_navigation_in_progress_by_client.get(client_id, False):
                sent = await self._send_start_navigation_event(session)
                if sent:
                    self._start_navigation_in_progress_by_client[client_id] = True
                else:
                    response = "No trip found to start navigation."
            else:
                self._logger.info(
                    "Start navigation already in progress, skipping event send client_id=%s",
                    client_id,
                )
                response = "Navigation is already in progress."

        # Envoyer un événement external_control pour show_deliveries
        if intent == "show_deliveries":
            await self._send_show_deliveries_event(session)

        return response

    async def _send_show_deliveries_event(self, session: Session) -> None:
        """
        Envoyer un événement external_control SHOW_DELIVERIES_LIST au client.
        """
        if self._ws_service is None:
            self._logger.warning("WebSocketService not set, cannot send external_control event")
            return

        # Envoyer l'événement external_control
        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.SHOW_DELIVERIES_LIST",
            "extras": {},
        }

        await self._ws_service.send(session, event)
        self._logger.info(
            "📋 External control sent client_id=%s action=SHOW_DELIVERIES_LIST",
            session.client_id,
        )

    async def _send_start_navigation_event(self, session: Session) -> bool:
        """
        Envoyer un événement external_control START_NAVIGATION au client.
        Lit le premier trip depuis data.json et envoie son ID.
        """
        if self._ws_service is None:
            self._logger.warning("WebSocketService not set, cannot send external_control event")
            return False

        # Lire le premier trip depuis data.json
        trip_id = await self._get_first_trip_id()

        if trip_id is None:
            self._logger.warning("No trip found in data.json, cannot send start_navigation event")
            return False

        # Envoyer l'événement external_control
        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.START_NAVIGATION",
            "extras": {
                "id": trip_id,
            },
        }

        await self._ws_service.send(session, event)
        self._logger.info(
            "🗺️ External control sent client_id=%s action=START_NAVIGATION trip_id=%s",
            session.client_id,
            trip_id,
        )
        return True

    async def _get_first_trip_id(self) -> str | None:
        """
        Lire le premier trip depuis data.json et retourner son ID.
        """
        try:
            if not self._data_file.exists():
                self._logger.warning("data.json not found")
                return None

            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or len(data) == 0:
                self._logger.warning("data.json is empty or not a list")
                return None

            # Prendre le premier trip qui n'est pas complété
            for trip in data:
                status = trip.get("deliveryStatus", "")
                if status != "COMPLETED":
                    trip_id = trip.get("id")
                    if trip_id:
                        return trip_id

            # Si tous sont complétés, prendre le premier quand même
            if data and isinstance(data[0], dict):
                return data[0].get("id")

            return None

        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error reading data.json: %s", e)
            return None

    def clear_start_navigation_in_progress(self, session: Session) -> None:
        """Réinitialiser l'état start_navigation pour une session."""
        self._start_navigation_in_progress_by_client.pop(session.client_id, None)

    async def _get_next_client_name(self) -> str | None:
        """
        Lire le premier client_name depuis data.json et retourner le nom.
        """
        try:
            if not self._data_file.exists():
                self._logger.warning("data.json not found")
                return None

            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or len(data) == 0:
                self._logger.warning("data.json is empty or not a list")
                return None

            # Prendre le premier trip qui n'est pas complété
            for trip in data:
                status = trip.get("deliveryStatus", "")
                if status != "COMPLETED":
                    client_name = trip.get("clientName")
                    if client_name:
                        return client_name

            # Si tous sont complétés, prendre le premier quand même
            if data and isinstance(data[0], dict):
                return data[0].get("clientName")

            return None

        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error reading data.json: %s", e)
            return None

    async def _get_next_delivery_address(self) -> str | None:
        """
        Lire le premier name (adresse) depuis data.json et retourner l'adresse.
        """
        try:
            if not self._data_file.exists():
                self._logger.warning("data.json not found")
                return None

            with open(self._data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list) or len(data) == 0:
                self._logger.warning("data.json is empty or not a list")
                return None

            # Prendre le premier trip qui n'est pas complété
            for trip in data:
                status = trip.get("deliveryStatus", "")
                if status != "COMPLETED":
                    name = trip.get("name")
                    if name:
                        return name

            # Si tous sont complétés, prendre le premier quand même
            if data and isinstance(data[0], dict):
                return data[0].get("name")

            return None

        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error reading data.json: %s", e)
            return None

    async def health_check(self) -> bool:
        """
        Health check : True si le service est opérationnel.
        """
        return True

    async def startup(self) -> None:
        """
        Initialisation du service (si nécessaire).
        """
        self._logger.info("ActionService started")

    async def shutdown(self) -> None:
        """
        Nettoyage du service (si nécessaire).
        """
        self._logger.info("ActionService shutdown")


class ActionResult:
    """
    Résultat de l'exécution d'une action.
    """

    def __init__(
        self,
        handled: bool,
        intent: str,
        text_to_llm: str | None,
        response: str | None,
    ):
        self.handled = handled  # True si l'action a été traitée localement
        self.intent = intent  # Nom de l'intention détectée
        self.text_to_llm = text_to_llm  # Texte à envoyer au LLM (si handled=False)
        self.response = response  # Réponse TTS (si handled=True)

    def __repr__(self) -> str:
        return (
            f"ActionResult(handled={self.handled}, intent={self.intent!r}, "
            f"text_to_llm={self.text_to_llm!r}, response={self.response!r})"
        )
