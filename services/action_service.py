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
    → Si action connue : exécute l'action, retourne soit une réponse locale,
      soit des données JSON à transmettre au LLM avec la question utilisateur
    → Envoie événement external_control au client via WebSocket
"""
from __future__ import annotations

import csv
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

    _SUPPORTED_LOCAL_INTENTS = (
        "start_navigation",
        "show_deliveries",
        "get_next_client_name",
        "get_next_delivery_address",
        "get_possible_delivery_failure_reason",
        "get_package_info",
        "show_map",
    )

    _LLM_DATA_FIELDS_BY_INTENT = {
        "get_next_client_name": "clientName",
        "get_next_delivery_address": "name",
        "get_package_info": "packageInfo",
    }

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
        Charger les intentions exécutées localement.

        On filtre la config sur :
          - les actions réellement supportées par ActionService
          - les intents encore présents dans le CSV d'intentions
        """
        logger = logging.getLogger(__name__)
        configured = tuple(
            str(intent).strip()
            for intent in getattr(config, "ACTION_KNOWN_INTENTS", self._SUPPORTED_LOCAL_INTENTS)
            if str(intent).strip()
        )
        available_from_csv = self._load_available_intents_from_csv()

        filtered: list[str] = []
        ignored: list[str] = []
        for intent in configured:
            if intent not in self._SUPPORTED_LOCAL_INTENTS:
                ignored.append(intent)
                continue
            if available_from_csv and intent not in available_from_csv:
                ignored.append(intent)
                continue
            filtered.append(intent)

        if not filtered:
            filtered = [
                intent
                for intent in self._SUPPORTED_LOCAL_INTENTS
                if not available_from_csv or intent in available_from_csv
            ]

        if ignored:
            logger.info("Ignored unsupported/stale action intents: %s", ", ".join(ignored))

        return tuple(filtered)

    def _load_available_intents_from_csv(self) -> set[str]:
        csv_path = Path(getattr(config, "INTENT_CSV_PATH", "intent_detection/intentions.csv"))
        try:
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                return {
                    str(row.get("intent", "")).strip()
                    for row in reader
                    if str(row.get("intent", "")).strip()
                }
        except FileNotFoundError:
            logging.getLogger(__name__).warning("Intent CSV not found: %s", csv_path)
            return set()
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to read intent CSV %s: %s", csv_path, exc)
            return set()

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
            return await self._handle_known_action(session, intent, transcription)

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

    async def _handle_known_action(
        self,
        session: Session,
        intent: str,
        transcription: str,
    ) -> ActionResult:
        """
        Exécuter une action connue et retourner soit une réponse locale,
        soit un contexte JSON à transmettre au LLM.

        Args:
            session: Session courante
            intent: Nom de l'intention (ex: "start_navigation")
            transcription: Texte original (peut servir pour le contexte)

        Returns:
            ActionResult décrivant soit une réponse locale, soit un forward au LLM
        """
        # Log l'intention pour débogage / action externe
        self._logger.info("ACTION: %s", intent)

        # Réponses par défaut pour chaque intention
        responses = {
            "start_navigation": "Starting navigation to the next destination.",
            "show_deliveries": "Here is the list of your deliveries.",
            "get_possible_delivery_failure_reason": "Here are the possible reasons for delivery failure.",
            "show_map": "Centering the map.",
        }

        if intent in self._LLM_DATA_FIELDS_BY_INTENT:
            llm_data = await self._get_llm_data_for_intent(intent)
            if llm_data:
                return ActionResult(
                    handled=False,
                    intent=intent,
                    text_to_llm=transcription,
                    response=None,
                    llm_data=llm_data,
                )

            fallback = {
                "get_next_client_name": "No client found.",
                "get_next_delivery_address": "No delivery address found.",
                "get_package_info": "No package info found.",
            }
            return ActionResult(
                handled=True,
                intent=intent,
                text_to_llm=None,
                response=fallback[intent],
            )

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

        # Recentrer la carte sur l'application Android
        if intent == "show_map":
            await self._send_show_map_event(session)

        return ActionResult(
            handled=True,
            intent=intent,
            text_to_llm=None,
            response=response,
        )

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

    async def _send_show_map_event(self, session: Session) -> None:
        """
        Envoyer un événement external_control RECENTER au client.
        """
        if self._ws_service is None:
            self._logger.warning("WebSocketService not set, cannot send external_control event")
            return

        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.RECENTER",
            "extras": {},
        }

        await self._ws_service.send(session, event)
        self._logger.info(
            "🧭 External control sent client_id=%s action=RECENTER",
            session.client_id,
        )

    def _read_trip_rows(self) -> list[dict]:
        if not self._data_file.exists():
            self._logger.warning("data.json not found")
            return []

        with open(self._data_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            self._logger.warning("data.json is not a list")
            return []

        return [trip for trip in data if isinstance(trip, dict)]

    def _get_first_planned_trip(self) -> dict | None:
        data = self._read_trip_rows()
        if not data:
            return None

        for trip in data:
            status = str(trip.get("deliveryStatus", "")).strip().lower()
            if status == "planned":
                return trip

        for trip in data:
            status = str(trip.get("deliveryStatus", "")).strip().upper()
            if status != "COMPLETED":
                return trip

        return data[0] if data else None

    async def _get_first_trip_id(self) -> str | None:
        """
        Lire le premier trip depuis data.json et retourner son ID.
        """
        try:
            trip = self._get_first_planned_trip()
            return trip.get("id") if trip else None

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
            trip = self._get_first_planned_trip()
            return trip.get("clientName") if trip else None

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
            trip = self._get_first_planned_trip()
            return trip.get("name") if trip else None

        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error reading data.json: %s", e)
            return None

    async def _get_package_info(self) -> str | None:
        """
        Lire le `packageInfo` du premier trip `planned` depuis data.json.
        """
        try:
            trip = self._get_first_planned_trip()
            if not trip:
                return None

            package_info = trip.get("packageInfo")
            if package_info is None:
                return None

            value = str(package_info).strip()
            return value or None

        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error reading data.json: %s", e)
            return None

    async def _get_llm_data_for_intent(self, intent: str) -> list[dict] | None:
        """
        Extraire les données JSON pertinentes pour un intent
        afin de les transmettre au LLM avec la question utilisateur.
        """
        field_name = self._LLM_DATA_FIELDS_BY_INTENT.get(intent)
        if not field_name:
            return None

        try:
            trip = self._get_first_planned_trip()
            if not trip:
                return None

            value = trip.get(field_name)
            if value is None:
                return None
            if isinstance(value, str) and not value.strip():
                return None

            return [
                {
                    "id": trip.get("id"),
                    "deliveryStatus": trip.get("deliveryStatus"),
                    field_name: value,
                }
            ]
        except json.JSONDecodeError as e:
            self._logger.error("Failed to parse data.json: %s", e)
            return None
        except Exception as e:
            self._logger.error("Error extracting LLM data from data.json: %s", e)
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
        llm_data: list[dict] | None = None,
    ):
        self.handled = handled  # True si l'action a été traitée localement
        self.intent = intent  # Nom de l'intention détectée
        self.text_to_llm = text_to_llm  # Texte à envoyer au LLM (si handled=False)
        self.response = response  # Réponse TTS (si handled=True)
        self.llm_data = llm_data  # Données JSON à fournir au LLM pour répondre

    def __repr__(self) -> str:
        return (
            f"ActionResult(handled={self.handled}, intent={self.intent!r}, "
            f"text_to_llm={self.text_to_llm!r}, response={self.response!r}, "
            f"llm_data={self.llm_data!r})"
        )
