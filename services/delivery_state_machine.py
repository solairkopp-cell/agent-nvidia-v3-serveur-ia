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


@dataclass
class StateMachineConfig:
    """Configuration de la machine à états."""
    max_retries: int = 2
    retry_tts: str = "Sorry, I didn't understand. Could you repeat?"
    fallback_tts: str = "Sorry, an error occurred. Let's start over."
    
    # STATE_1
    ask_completion_tts: str = "Is the delivery completed?"
    yes_patterns: tuple = ("yes", "yep", "yeah")
    no_patterns: tuple = ("no", "nope")
    
    # STATE_2
    ask_reason_tts: str = "Can you tell me why?"
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
    
    def reset(self):
        self.mode = Mode.MODE_0
        self.state = State.STATE_0
        self.retry_count = 0
        self.current_trip_id = None
        self.failure_reason = None
        self.failure_reason_index = None


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
    ):
        self.config = config or StateMachineConfig()
        self._contexts: dict[str, StateContext] = {}  # client_id -> StateContext
        self._planning_service = None
        self._lock = asyncio.Lock()
        self._intent_detector = intent_detector
    
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
            return self.ProcessResult(
                should_handle=True,
                tts_response="Delivery is marked as completed.",
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

                return self.ProcessResult(
                    should_handle=True,
                    tts_response="Delivery has been marked as failure.",
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

        → MODE_0 (ignore l'input utilisateur)
        """
        logger.info(
            "STATE_5: exiting to MODE_0 client_id=%s",
            session.client_id,
        )

        # Reset complet
        ctx.reset()

        # Si l'utilisateur a parlé pendant le TTS, on ignore et on sort
        return self.ProcessResult(
            should_handle=True,
            tts_response=None,
            next_state=State.STATE_0,
            action="exit_to_mode_0",
        )
    
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
            
            script_dir = Path(__file__).parent.parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)
            
            try:
                # Appeler la méthode de mise à jour
                # Note: adapter selon l'API réelle de PlanningService
                result = await planning_service.update_trip_status(
                    trip_id=trip_id,
                    status=status,
                    reason=reason,
                )
                logger.info(
                    "Trip %s updated: status=%s, reason=%s",
                    trip_id,
                    status,
                    reason or "N/A",
                )
                return result is not None
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
