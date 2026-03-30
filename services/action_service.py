"""
services/action_service.py
Gestion des actions connues après la détection d'intention.

Responsabilité :
  - Recevoir l'intention détectée et la transcription
  - Si intention = "INCONNU" → retourner la transcription pour le LLM
  - Si intention = action connue (start_navigation, show_deliveries, etc.) → exécuter l'action localement
  - Ne PAS envoyer les actions connues au LLM (économie de ressources)

Flux :
  transcription + intention → ActionService.execute()
    → Si INCONNU : retourne {"action": "forward_to_llm", "text": transcription}
    → Si action connue : exécute l'action, retourne {"action": "handled", "intent": "...", "response": "..."}
"""
from __future__ import annotations

import logging
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
        # À personnaliser selon tes besoins réels (appels API, base de données, etc.)
        responses = {
            "start_navigation": "Starting navigation to the next destination.",
            "show_deliveries": "Here is the list of your deliveries.",
            "repeat_last_sentence": "Repeating: " + (session.conversation_history[-1]["content"] if session.conversation_history else "nothing"),
            "get_next_client_name": "Retrieving the next client's name.",
            "get_next_delivery_address": "Retrieving the address of the next delivery.",
            "get_possible_delivery_failure_reason": "Here are the possible reasons for delivery failure.",
            "stop_listening": "Disabling listening.",
        }

        response = responses.get(intent, f"Action {intent} exécutée.")

        # Ici tu peux ajouter la logique réelle pour chaque intention :
        # - Appeler une API de navigation
        # - Interroger une base de données
        # - Modifier l'état de la session
        # - Envoyer un événement WebSocket au client

        return response

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
