"""
services/delivery_state_machine.py
Machine à états pour la complétion de livraison.

Modes:
  - MODE_0: Normal (STT → IntentDetector → KNOWN/UNKNOWN → TTS/LLM)
  - MODE_1: Delivery completion flow (STT → Normalize → pattern matching → action)

États MODE_1:
  - STATE_1 (ASK_COMPLETION): "Is the delivery completed?"
  - STATE_2 (ASK_REASON): "Can you tell me why?"
  - STATE_4 (COMPLETE): Update trip status
  - STATE_5 (EXIT): Return to MODE_0
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Callable, Awaitable

if TYPE_CHECKING:
    from models.session import Session

logger = logging.getLogger(__name__)


class Mode(Enum):
    MODE_0 = "mode_0"  # Normal flow
    MODE_1 = "mode_1"  # Delivery completion flow


class State(Enum):
    STATE_0 = "state_0"  # MODE_0 normal operation
    STATE_1 = "state_1"  # ASK_COMPLETION
    STATE_2 = "state_2"  # ASK_REASON
    STATE_4 = "state_4"  # COMPLETE
    STATE_5 = "state_5"  # EXIT
    STATE_6 = "state_6"  # ASK_PHOTO


@dataclass
class StateMachineConfig:
    """Configuration de la machine à états."""
    max_retries: int = 2
    retry_tts: str = "Sorry, I didn't understand. Could you repeat?"
    fallback_tts: str = "Sorry, an error occurred. Let's start over."
    
    # STATE_1
    ask_completion_tts: str = "you have arrived at the destination. may I ask if the delivery is completed?"
    yes_patterns: tuple = ("yes", "yep", "yeah")
    no_patterns: tuple = ("no", "nope")
    
    # STATE_2
    ask_reason_tts: str = "Can you give me a reason ? You can say 'list' to hear the options or ask for it ."
    list_trigger: str = "list"
    reason_list: tuple = (
        "Customer not available",
        "Wrong address",
        "Package damaged",
        "Access denied",
        "Vehicle breakdown",
        "Other",
    )
    
    # STATE_4
    success_status: str = "COMPLETED"
    failure_status: str = "FAILED"


@dataclass
class StateContext:
    """Contexte de la session dans la machine à états."""
    mode: Mode = Mode.MODE_0
    state: State = State.STATE_0
    retry_count: int = 0
    current_trip_id: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_reason_index: Optional[int] = None
    # Pour demande photo
    photo_trip_id: Optional[str] = None
    photo_delivery_id: Optional[str] = None
    photo_address: Optional[str] = None

    def reset(self):
        self.mode = Mode.MODE_0
        self.state = State.STATE_0
        self.retry_count = 0
        self.current_trip_id = None
        self.failure_reason = None
        self.failure_reason_index = None
        self.photo_trip_id = None
        self.photo_delivery_id = None
        self.photo_address = None


class NumberExtractor:
    """Extrait les nombres de la parole transcrite."""
    
    # Mapping des nombres en chiffres (français/anglais)
    NUMBER_WORDS = {
        "one": 1, "un": 1, "une": 1, "first": 1, "premier": 1, "première": 1,
        "two": 2, "deux": 2, "second": 2, "deuxième": 2,
        "three": 3, "trois": 3, "third": 3, "troisième": 3,
        "four": 4, "quatre": 4, "fourth": 4, "quatrième": 4,
        "five": 5, "cinq": 5, "fifth": 5, "cinquième": 5,
        "six": 6, "six": 6, "sixth": 6, "sixième": 6,
        "seven": 7, "sept": 7, "seventh": 7, "septième": 7,
        "eight": 8, "huit": 8, "eighth": 8, "huitième": 8,
        "nine": 9, "neuf": 9, "ninth": 9, "neuvième": 9,
        "ten": 10, "dix": 10, "tenth": 10, "dixième": 10,
    }
    
    @classmethod
    def extract(cls, text: str) -> Optional[int]:
        """
        Extrait un nombre du texte.
        Retourne l'index (1-based) ou None.
        """
        text = text.lower().strip()

        # Chercher un chiffre direct
        digits = re.findall(r'\b(\d+)\b', text)
        if digits:
            return int(digits[0])

        # Chercher un mot-nombre (en nettoyant la ponctuation)
        words = re.findall(r'\b\w+\b', text)
        for word in words:
            if word in cls.NUMBER_WORDS:
                return cls.NUMBER_WORDS[word]

        return None


class DeliveryStateMachine:
    """
    Machine à états pour la gestion de complétion de livraison.

    Usage:
        state_machine = DeliveryStateMachine()
        await state_machine.startup()

        # Dans le pipeline STT:
        result = await state_machine.process_input(session, transcript)
        if result.should_handle:
            # La machine à états a géré l'input
            await state_machine.say(session, result.tts_response)
        else:
            # Passer au pipeline normal (MODE_0)
    """

    def __init__(
        self,
        config: Optional[StateMachineConfig] = None,
        intent_detector=None,
        ws_service=None,
        agent_service=None,
    ):
        self.config = config or StateMachineConfig()
        self._contexts: dict[str, StateContext] = {}  # client_id -> StateContext
        self._planning_service = None
        self._lock = asyncio.Lock()
        self._intent_detector = intent_detector
        self._ws_service = ws_service
        self._agent_service = agent_service
    
    async def startup(self):
        """Initialisation au démarrage."""
        logger.info("DeliveryStateMachine started")
    
    async def shutdown(self):
        """Nettoyage à l'arrêt."""
        self._contexts.clear()
        logger.info("DeliveryStateMachine shutdown")
    
    def _get_context(self, session: "Session") -> StateContext:
        """Récupère ou crée le contexte pour une session."""
        if session.client_id not in self._contexts:
            self._contexts[session.client_id] = StateContext()
        return self._contexts[session.client_id]
    
    def _clear_context(self, session: "Session"):
        """Supprime le contexte d'une session."""
        self._contexts.pop(session.client_id, None)
    
    # ── Entry Points ─────────────────────────────────────────────────────────
    
    async def enter_mode_1(self, session: "Session", trip_id: Optional[str] = None):
        """
        Entrer dans le MODE_1 (delivery completion flow).
        Déclenche STATE_1 automatiquement.
        """
        ctx = self._get_context(session)
        ctx.mode = Mode.MODE_1
        ctx.state = State.STATE_1
        ctx.current_trip_id = trip_id
        ctx.retry_count = 0
        
        logger.info(
            "State machine: entered MODE_1 → STATE_1 client_id=%s trip_id=%s",
            session.client_id,
            trip_id,
        )
    
    async def exit_to_mode_0(self, session: "Session"):
        """
        Sortir vers MODE_0 (normal flow).
        """
        ctx = self._get_context(session)
        ctx.reset()
        
        logger.info("State machine: exited to MODE_0 client_id=%s", session.client_id)
    
    # ── Processing ───────────────────────────────────────────────────────────
    
    @dataclass
    class ProcessResult:
        """Résultat du traitement d'un input."""
        should_handle: bool  # True si la machine à états a géré l'input
        tts_response: Optional[str]  # Texte à envoyer au TTS
        next_state: Optional[State]  # Prochain état
        action: Optional[str]  # Action à exécuter (ex: "update_trip")
        action_params: dict = field(default_factory=dict)  # Paramètres de l'action
    
    async def process_input(
        self,
        session: "Session",
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        Traiter un transcript STT dans le contexte de la machine à états.
        
        Returns:
            ProcessResult avec:
              - should_handle=True si la machine à états gère cet input
              - tts_response: texte à synthétiser
              - next_state: prochain état (si transition)
              - action: action à exécuter (ex: "update_trip")
              - action_params: paramètres pour l'action
        """
        ctx = self._get_context(session)
        
        # Si on est en MODE_0, on ne gère pas
        if ctx.mode == Mode.MODE_0:
            return self.ProcessResult(
                should_handle=False,
                tts_response=None,
                next_state=None,
                action=None,
            )
        
        # Router vers le handler d'état approprié
        if ctx.state == State.STATE_1:
            return await self._handle_state_1(session, ctx, transcript)
        elif ctx.state == State.STATE_2:
            return await self._handle_state_2(session, ctx, transcript)
        elif ctx.state == State.STATE_4:
            return await self._handle_state_4(session, ctx, transcript)
        elif ctx.state == State.STATE_5:
            return await self._handle_state_5(session, ctx, transcript)
        elif ctx.state == State.STATE_6:
            return await self._handle_state_6(session, ctx, transcript)

        # État inconnu → reset
        logger.warning("Unknown state %s for client_id=%s", ctx.state, session.client_id)
        return await self._trigger_fallback(session, ctx)
    
    # ── State Handlers ───────────────────────────────────────────────────────
    
    async def _handle_state_1(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        STATE_1: ASK_COMPLETION
        "Is the delivery completed?"
        
        YES → STATE_4 (SUCCESS)
        NO  → STATE_2
        INVALID/TIMEOUT → retry (max 2)
        fallback → reset STATE_1
        """
        text_lower = transcript.lower().strip()

        # Vérifier YES
        if any(pattern in text_lower for pattern in self.config.yes_patterns):
            logger.info(
                "STATE_1: YES detected client_id=%s",
                session.client_id,
            )
            
            # Trouver le trip suivant et préparer l'annonce
            next_trip_info = await self._get_next_trip_info(session)
            announcement = "the delivery has been marked as completed."
            
            if next_trip_info:
                next_trip_id, next_address, next_client_name = next_trip_info
                
                # Annoncer la prochaine livraison
                announcement = (
                    f"the delivery is now completed. "
                    f"You are now heading to {next_address}. "
                    f"The client is {next_client_name}."
                )
                
                logger.info(
                    "STATE_1: next trip announced client_id=%s trip_id=%s address=%s client=%s",
                    session.client_id,
                    next_trip_id,
                    next_address,
                    next_client_name,
                )
                
                # Démarrer automatiquement la navigation (après le TTS)
                # On utilise un call_later pour attendre la fin du TTS
                asyncio.create_task(
                    self._trigger_start_navigation_delayed(session, next_trip_id, delay=3.0)
                )
            
            return self.ProcessResult(
                should_handle=True,
                tts_response=announcement,
                next_state=State.STATE_5,
                action="update_trip",
                action_params={"status": self.config.success_status},
            )

        # Vérifier NO
        if any(pattern in text_lower for pattern in self.config.no_patterns):
            logger.info(
                "STATE_1: NO detected client_id=%s → STATE_2",
                session.client_id,
            )
            return self.ProcessResult(
                should_handle=True,
                tts_response=self.config.ask_reason_tts,
                next_state=State.STATE_2,
                action=None,
            )
        
        # Input invalide → retry ou fallback
        ctx.retry_count += 1
        if ctx.retry_count <= self.config.max_retries:
            logger.info(
                "STATE_1: invalid input (retry %d/%d) client_id=%s",
                ctx.retry_count,
                self.config.max_retries,
                session.client_id,
            )
            return self.ProcessResult(
                should_handle=True,
                tts_response=self.config.retry_tts,
                next_state=State.STATE_1,
                action=None,
            )
        
        # Trop de retries → fallback
        logger.warning(
            "STATE_1: max retries exceeded client_id=%s",
            session.client_id,
        )
        return await self._trigger_fallback(session, ctx)
    
    async def _handle_state_2(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        STATE_2: ASK_REASON
        "Can you tell me why?"

        Intent "get_possible_delivery_failure_reason" → read reasons aloud → stay STATE_2
        anything else → NumberExtractor →
            NUMBER found → STATE_4 (FAILURE)
            NO NUMBER   → retry (max 2)
        fallback → reset STATE_1
        """
        text_lower = transcript.lower().strip()

        # Vérifier l'intent "get_possible_delivery_failure_reason" via intent detection
        if self._intent_detector is not None:
            try:
                detected_intent = self._intent_detector.getint(transcript)
                if detected_intent == "get_possible_delivery_failure_reason":
                    logger.info(
                        "STATE_2: failure reason list requested via intent client_id=%s",
                        session.client_id,
                    )
                    # Formater la liste des raisons
                    list_text = "Failure reasons: " + ", ".join(
                        f"{i+1}. {reason}"
                        for i, reason in enumerate(self.config.reason_list)
                    )
                    return self.ProcessResult(
                        should_handle=True,
                        tts_response=list_text,
                        next_state=State.STATE_2,
                        action=None,
                    )
            except Exception:
                logger.exception("Intent detection error in state machine client_id=%s", session.client_id)

        # Fallback: vérifier l'ancien mot-clé "list"
        if self.config.list_trigger in text_lower:
            logger.info(
                "STATE_2: list requested (fallback) client_id=%s",
                session.client_id,
            )
            # Formater la liste des raisons
            list_text = "Failure reasons: " + ", ".join(
                f"{i+1}. {reason}"
                for i, reason in enumerate(self.config.reason_list)
            )
            return self.ProcessResult(
                should_handle=True,
                tts_response=list_text,
                next_state=State.STATE_2,
                action=None,
            )

        # Extraire un nombre
        number = NumberExtractor.extract(text_lower)
        if number is not None:
            # Valider l'index
            if 1 <= number <= len(self.config.reason_list):
                reason_index = number - 1
                reason = self.config.reason_list[reason_index]

                logger.info(
                    "STATE_2: reason selected #%d: %s client_id=%s",
                    number,
                    reason,
                    session.client_id,
                )

                ctx.failure_reason = reason
                ctx.failure_reason_index = reason_index

                # Reason 1 = "Customer not available" → demander photo
                if reason_index == 0:  # Index 0 = première raison
                    # Sauvegarder les infos du trip actuel pour la demande photo
                    ctx.photo_trip_id = ctx.current_trip_id
                    ctx.photo_delivery_id = ctx.current_trip_id
                    ctx.photo_address = "the delivery location"
                    
                    logger.info(
                        "STATE_2: reason 1 selected → requesting photo client_id=%s",
                        session.client_id,
                    )
                    
                    # Envoyer immédiatement l'événement ask_photo_event
                    await self._send_ask_photo_event(session, ctx)
                    
                    return self.ProcessResult(
                        should_handle=True,
                        tts_response="Can you please take a photo of the package?",
                        next_state=State.STATE_6,  # Attendre photo_taken ou photo_not_taken
                        action=None,  # Pas encore de update_trip
                    )

                # Autres raisons → directement failure + annonce suite
                # Trouver le trip suivant et préparer l'annonce
                next_trip_info = await self._get_next_trip_info(session)
                announcement = "Delivery has been marked as failure."

                if next_trip_info:
                    next_trip_id, next_address, next_client_name = next_trip_info

                    # Annoncer la prochaine livraison
                    announcement = (
                        f"Delivery is a failure. "
                        f"You are now heading to {next_address}. "
                        f"The client is {next_client_name}."
                    )

                    logger.info(
                        "STATE_2: next trip announced after failure client_id=%s trip_id=%s address=%s client=%s",
                        session.client_id,
                        next_trip_id,
                        next_address,
                        next_client_name,
                    )

                    # Démarrer automatiquement la navigation (après le TTS)
                    asyncio.create_task(
                        self._trigger_start_navigation_delayed(session, next_trip_id, delay=3.0)
                    )

                return self.ProcessResult(
                    should_handle=True,
                    tts_response=announcement,
                    next_state=State.STATE_5,
                    action="update_trip",
                    action_params={
                        "status": self.config.failure_status,
                        "reason": reason,
                    },
                )
            else:
                # Numéro hors limite
                invalid_msg = f"Please choose a number between 1 and {len(self.config.reason_list)}"
                ctx.retry_count += 1
                if ctx.retry_count <= self.config.max_retries:
                    return self.ProcessResult(
                        should_handle=True,
                        tts_response=invalid_msg,
                        next_state=State.STATE_2,
                        action=None,
                    )
                return await self._trigger_fallback(session, ctx)
        
        # Pas de nombre détecté → retry
        ctx.retry_count += 1
        if ctx.retry_count <= self.config.max_retries:
            logger.info(
                "STATE_2: no number detected (retry %d/%d) client_id=%s",
                ctx.retry_count,
                self.config.max_retries,
                session.client_id,
            )
            return self.ProcessResult(
                should_handle=True,
                tts_response=self.config.retry_tts,
                next_state=State.STATE_2,
                action=None,
            )
        
        # Trop de retries → fallback
        logger.warning(
            "STATE_2: max retries exceeded client_id=%s",
            session.client_id,
        )
        return await self._trigger_fallback(session, ctx)
    
    async def _handle_state_4(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        STATE_4: COMPLETE

        SUCCESS → planning.update_trip(status="COMPLETED")
        FAILURE → planning.update_trip(status="FAILED", reason=N)
        → STATE_5
        """
        # L'action update_trip est déjà définie dans le résultat précédent
        # Ici on transitionne juste vers STATE_5
        logger.info(
            "STATE_4: trip updated client_id=%s → STATE_5",
            session.client_id,
        )

        return self.ProcessResult(
            should_handle=True,
            tts_response=None,
            next_state=State.STATE_5,
            action=None,
        )
    
    async def _handle_state_5(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        STATE_5: EXIT

        → MODE_0 (sans annonce, déjà faite dans STATE_1 ou STATE_2)
        """
        logger.info(
            "STATE_5: exiting to MODE_0 client_id=%s",
            session.client_id,
        )

        # Reset complet
        ctx.reset()

        # Pas d'annonce ici : déjà faite dans STATE_1 (YES) ou STATE_2 (NO)
        return self.ProcessResult(
            should_handle=True,
            tts_response=None,
            next_state=State.STATE_0,
            action="exit_to_mode_0",
        )

    async def _handle_state_6(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        STATE_6: ASK_PHOTO

        Envoie ask_photo_event au client et attend photo_taken ou photo_not_taken.
        """
        logger.info(
            "STATE_6: asking for photo client_id=%s",
            session.client_id,
        )
        
        # Envoyer l'événement ask_photo_event au client
        await self._send_ask_photo_event(session, ctx)
        
        # Retourner None pour attendre un événement (pas de réponse TTS)
        # Le client répondra avec photo_taken ou photo_not_taken
        return self.ProcessResult(
            should_handle=True,
            tts_response=None,  # Pas de TTS, on attend l'événement
            next_state=State.STATE_6,  # Reste dans STATE_6 jusqu'à réponse
            action=None,
        )

    async def _send_ask_photo_event(self, session: "Session", ctx: StateContext) -> None:
        """
        Envoyer l'événement ask_photo_event au client.
        """
        if self._ws_service is None:
            logger.warning("WebSocketService not available for ask_photo_event")
            return

        from datetime import datetime

        trip_id = ctx.photo_trip_id or ctx.current_trip_id
        delivery_id = ctx.photo_delivery_id or ctx.current_trip_id
        address = ctx.photo_address or "unknown"

        event = {
            "type": "ask_photo_event",
            "trip_id": trip_id,
            "delivery_id": delivery_id,
            "address": address,
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            await self._ws_service.send(session, event)
            logger.info(
                "📸 ask_photo_event sent client_id=%s trip_id=%s",
                session.client_id,
                trip_id,
            )
        except Exception as e:
            logger.error("Error sending ask_photo_event: %s", e)

    async def _send_emotion(self, session: "Session", name: str) -> None:
        """
        Envoyer un événement émotion au client.
        
        Args:
            session: Session WebSocket
            name: Nom de l'émotion ('happy', 'sad', 'greeting', 'speaking')
        """
        if self._ws_service is None:
            logger.warning("WebSocketService not available for emotion event")
            return

        event = {
            "type": "emotion",
            "name": name,
        }

        try:
            await self._ws_service.send(session, event)
            logger.info(
                "😊 Emotion sent client_id=%s name=%s",
                session.client_id,
                name,
            )
        except Exception as e:
            logger.error("Error sending emotion: %s", e)

    async def handle_photo_response(
        self,
        session: "Session",
        photo_taken: bool,
    ) -> None:
        """
        Gérer la réponse photo_taken ou photo_not_taken du client.
        """
        logger.info(
            "📸 Photo response received client_id=%s photo_taken=%s",
            session.client_id,
            photo_taken,
        )
        
        ctx = self._get_context(session)
        
        if photo_taken:
            # Photo prise → succès + annonce suite
            trip_id = ctx.photo_trip_id or ctx.current_trip_id
            
            # Mettre à jour le trip
            if trip_id:
                await self.update_trip_status(
                    driver_serial=session.driver_serial,
                    trip_id=trip_id,
                    status="COMPLETED",
                )
            
            # Annoncer la suite et démarrer navigation
            await self._announce_next_trip_and_start_navigation(session, success=True)
        else:
            # Photo non prise → échec + annonce suite
            trip_id = ctx.photo_trip_id or ctx.current_trip_id
            reason = ctx.failure_reason or "Other"
            
            # Mettre à jour le trip en FAILED
            if trip_id:
                await self.update_trip_status(
                    driver_serial=session.driver_serial,
                    trip_id=trip_id,
                    status="FAILED",
                    reason=reason,
                )
            
            # Annoncer la suite et démarrer navigation
            await self._announce_next_trip_and_start_navigation(session, success=False)
        
        # Reset et retour à MODE_0
        ctx.reset()

    async def _announce_next_trip_and_start_navigation(
        self,
        session: "Session",
        success: bool,
    ) -> None:
        """
        Annoncer la prochaine livraison et démarrer la navigation.
        """
        next_trip_info = await self._get_next_trip_info(session)

        if next_trip_info:
            next_trip_id, next_address, next_client_name, is_last = next_trip_info

            # Envoyer l'émotion avant l'annonce
            emotion = "happy" if success else "sad"
            await self._send_emotion(session, emotion)

            # Si c'est la dernière livraison, envoyer l'émotion "end"
            if is_last:
                await self._send_emotion(session, "end")

            # Annoncer
            if success:
                if is_last:
                    announcement = (
                        f"Delivery completed successfully. "
                        f"You are now heading to {next_address}. "
                        f"The client is {next_client_name}. "
                        f"This is your last delivery."
                    )
                else:
                    announcement = (
                        f"Delivery completed successfully. "
                        f"You are now heading to {next_address}. "
                        f"The client is {next_client_name}."
                    )
            else:
                if is_last:
                    announcement = (
                        f"Delivery has been marked as failure. "
                        f"You are now heading to {next_address}. "
                        f"The client is {next_client_name}. "
                        f"This is your last delivery."
                    )
                else:
                    announcement = (
                        f"Delivery has been marked as failure. "
                        f"You are now heading to {next_address}. "
                        f"The client is {next_client_name}."
                    )

            logger.info(
                "📢 Next trip announced client_id=%s address=%s client=%s is_last=%s",
                session.client_id,
                next_address,
                next_client_name,
                is_last,
            )

            # Parler l'annonce via AgentService
            if self._agent_service:
                await self._agent_service.speak_text(session, announcement)

            # Démarrer navigation après le TTS (délai pour lecture annonce)
            asyncio.create_task(
                self._trigger_start_navigation_delayed(session, next_trip_id, delay=3.0)
            )
        else:
            # Pas de trip suivant
            logger.info(
                "📢 No next trip client_id=%s",
                session.client_id,
            )

    async def _get_next_trip_info(self, session: "Session") -> tuple | None:
        """
        Trouver le trip qui suit celui qui vient d'être complété.

        Returns:
            (trip_id, address, client_name, is_last) ou None
        """
        import json
        from pathlib import Path

        data_file = Path("data.json")

        try:
            if not data_file.exists():
                return None

            with open(data_file, "r", encoding="utf-8") as f:
                trips = json.load(f)

            if not isinstance(trips, list) or len(trips) == 0:
                return None

            # Trouver l'index du trip actuel
            current_trip_id = session.current_trip_id
            current_index = -1

            for i, trip in enumerate(trips):
                if trip.get("id") == current_trip_id:
                    current_index = i
                    break

            # Le trip suivant est juste après
            next_index = current_index + 1

            if next_index >= len(trips):
                return None  # Dernier trip

            next_trip = trips[next_index]

            # Vérifier qu'il n'est pas complété
            status = next_trip.get("deliveryStatus", "")
            if status == "COMPLETED":
                # Chercher le premier non-complété après
                for j in range(next_index + 1, len(trips)):
                    trip = trips[j]
                    if trip.get("deliveryStatus", "") != "COMPLETED":
                        next_trip = trip
                        break
                else:
                    return None  # Tous complétés

            trip_id = next_trip.get("id")
            # Adresse : utiliser le champ name (3 premiers mots)
            full_name = next_trip.get("name", "unknown address")
            address = " ".join(full_name.split()[:3]) if full_name else "unknown address"

            client_name = next_trip.get("clientName", "unknown client")

            # Vérifier si c'est le dernier trip (aucun trip non-complété après)
            is_last = True
            for j in range(current_index + 2, len(trips)):
                trip = trips[j]
                if trip.get("deliveryStatus", "") != "COMPLETED":
                    is_last = False
                    break

            return (trip_id, address, client_name, is_last)

        except Exception as e:
            logger.error("Error getting next trip: %s", e)
            return None

    async def _trigger_start_navigation(
        self,
        session: "Session",
        trip_id: str,
    ) -> None:
        """
        Envoyer automatiquement l'événement start_navigation au client.
        """
        if self._ws_service is None:
            return

        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.START_NAVIGATION",
            "extras": {
                "id": trip_id,
            },
        }

        try:
            await self._ws_service.send(session, event)
            logger.info(
                "🗺️ Auto start_navigation sent client_id=%s trip_id=%s",
                session.client_id,
                trip_id,
            )
        except Exception as e:
            logger.error("Error sending start_navigation: %s", e)

    async def _trigger_start_navigation_delayed(
        self,
        session: "Session",
        trip_id: str,
        delay: float = 3.0,
    ) -> None:
        """
        Envoyer start_navigation après un délai (pour attendre la fin du TTS).
        """
        await asyncio.sleep(delay)
        await self._trigger_start_navigation(session, trip_id)

    # ── Helpers ──────────────────────────────────────────────────────────────
    
    async def _trigger_fallback(
        self,
        session: "Session",
        ctx: StateContext,
    ) -> "DeliveryStateMachine.ProcessResult":
        """
        Déclencher le fallback: TTS "Sorry..." → reset STATE_1.
        """
        ctx.reset()
        ctx.mode = Mode.MODE_1
        ctx.state = State.STATE_1

        # Message fallback + repose la question STATE_1
        fallback_message = (
            f"{self.config.fallback_tts} "
            f"{self.config.ask_completion_tts}"
        )

        return self.ProcessResult(
            should_handle=True,
            tts_response=fallback_message,
            next_state=State.STATE_1,
            action=None,
        )
    
    # ── Planning Service Integration ─────────────────────────────────────────
    
    async def update_trip_status(
        self,
        driver_serial: str,
        trip_id: str,
        status: str,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Mettre à jour le statut d'un trip via PlanningService.
        
        Args:
            driver_serial: Numéro de série du driver
            trip_id: ID du trip à mettre à jour
            status: "COMPLETED" ou "FAILED"
            reason: Raison de l'échec (si status="FAILED")
        
        Returns:
            True si la mise à jour a réussi
        """
        import sys
        from pathlib import Path
        
        sys.path.insert(0, str(Path(__file__).parent.parent / "data_base_service"))
        
        try:
            from service.planning_service import PlanningService
            from service import TokenManager
            from entities.enum.package_status import PackageStatus

            script_dir = Path(__file__).parent.parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)

            try:
                # Convertir le status en enum PackageStatus
                if status == "COMPLETED":
                    package_status = PackageStatus.DELIVERED_SUCCESSFULLY
                elif status == "FAILED":
                    package_status = PackageStatus.DELIVERY_FAILURE
                else:
                    package_status = PackageStatus.PLANNED

                # Mettre à jour le statut du package
                result = await planning_service.update_package_status(
                    package_id=trip_id,
                    new_status=package_status,
                )
                
                # Si échec, ajouter la raison
                if status == "FAILED" and reason and result:
                    await planning_service.add_delivery_failure(
                        package_id=trip_id,
                        cause=1,  # Cause générique
                        comment=reason,
                    )
                
                logger.info(
                    "Package %s updated: status=%s, reason=%s",
                    trip_id,
                    status,
                    reason or "N/A",
                )
                return result
            finally:
                await planning_service.close()

        except Exception as e:
            logger.exception("Failed to update trip status: %s", e)
            return False
    
    # ── Session Management ───────────────────────────────────────────────────
    
    def get_session_state(self, session: "Session") -> tuple[Mode, State]:
        """
        Récupérer l'état actuel d'une session.
        
        Returns:
            (mode, state) tuple
        """
        ctx = self._get_context(session)
        return ctx.mode, ctx.state
    
    def is_in_mode_1(self, session: "Session") -> bool:
        """
        Vérifier si une session est en MODE_1.
        """
        ctx = self._get_context(session)
        return ctx.mode == Mode.MODE_1
