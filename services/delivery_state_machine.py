"""
services/delivery_state_machine.py
Machine à états pour la complétion de livraison.

Modes:
  - MODE_0: Normal (STT → LLM → TTS)
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
from typing import TYPE_CHECKING, Optional

from services import utility_service

if TYPE_CHECKING:
    from models.session import Session

logger = logging.getLogger(__name__)


class Mode(Enum):
    MODE_0 = "mode_0"
    MODE_1 = "mode_1"


class State(Enum):
    STATE_0 = "state_0"
    STATE_1 = "state_1"  # ASK_COMPLETION
    STATE_2 = "state_2"  # ASK_REASON
    STATE_4 = "state_4"  # COMPLETE
    STATE_5 = "state_5"  # EXIT
    STATE_6 = "state_6"  # ASK_PHOTO


@dataclass
class StateMachineConfig:
    max_retries: int = 2
    retry_tts: str = "Sorry, I didn't understand. Could you repeat?"
    fallback_tts: str = "Sorry, an error occurred. Let's start over."

    # STATE_1
    ask_completion_tts: str = "You have arrived at the destination. Is the delivery completed?"
    yes_patterns: tuple = ("yes", "yep", "yeah")
    no_patterns: tuple = ("no", "nope")
    invalid_yes_no_tts: str = "Please answer with yes or no."

    # STATE_2
    ask_reason_tts: str = "Can you give me a reason? Say 'list' to hear the options."
    list_trigger: str = "list"
    reason_list: tuple = (
        "Customer not available",
        "Wrong address",
        "Package damaged",
        "Access denied",
        "Vehicle breakdown",
        "Other",
    )
    invalid_number_tts: str = "Please choose a valid number from the list."
    ask_photo_tts: str = "Please take a photo of the package to validate the delivery."

    # STATE_4
    success_status: str = "COMPLETED"
    failure_status: str = "FAILED"

    # Announcements
    delivery_completed_tts: str = "The delivery has been marked as completed."
    delivery_failed_tts: str = "The delivery has been marked as failure."
    last_delivery_suffix: str = " This is your last delivery."
    route_finished_tts: str = " The route is now finished."
    next_heading_tts: str = " You are now heading to {address}. The client is {client}."
    delivery_validated_tts: str = "Delivery validated."


@dataclass
class StateContext:
    mode: Mode = Mode.MODE_0
    state: State = State.STATE_0
    retry_count: int = 0
    current_trip_id: Optional[str] = None
    failure_reason: Optional[str] = None
    failure_reason_index: Optional[int] = None
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
    NUMBER_WORDS = {
        "one": 1, "un": 1, "une": 1, "first": 1, "premier": 1, "première": 1,
        "two": 2, "deux": 2, "second": 2, "deuxième": 2,
        "three": 3, "trois": 3, "third": 3, "troisième": 3,
        "four": 4, "quatre": 4, "fourth": 4, "quatrième": 4,
        "five": 5, "cinq": 5, "fifth": 5, "cinquième": 5,
        "six": 6, "sixth": 6, "sixième": 6,
        "seven": 7, "sept": 7, "seventh": 7, "septième": 7,
        "eight": 8, "huit": 8, "eighth": 8, "huitième": 8,
        "nine": 9, "neuf": 9, "ninth": 9, "neuvième": 9,
        "ten": 10, "dix": 10, "tenth": 10, "dixième": 10,
    }

    @classmethod
    def extract(cls, text: str) -> Optional[int]:
        text = text.lower().strip()
        digits = re.findall(r'\b(\d+)\b', text)
        if digits:
            return int(digits[0])
        words = re.findall(r'\b\w+\b', text)
        for word in words:
            if word in cls.NUMBER_WORDS:
                return cls.NUMBER_WORDS[word]
        return None


class DeliveryStateMachine:
    """
    Machine à états pour la gestion de complétion de livraison.
    Aucun LLM : toutes les réponses sont hardcodées et envoyées directement au TTS.
    """

    def __init__(
        self,
        config: Optional[StateMachineConfig] = None,
        ws_service=None,
        agent_service=None,
    ):
        self.config = config or StateMachineConfig()
        self._contexts: dict[str, StateContext] = {}
        self._lock = asyncio.Lock()
        self._ws_service = ws_service
        self._agent_service = agent_service
        self.utility_service = utility_service.UtilityService()

    async def startup(self):
        logger.info("DeliveryStateMachine started")

    async def shutdown(self):
        self._contexts.clear()
        logger.info("DeliveryStateMachine shutdown")

    def _get_context(self, session: "Session") -> StateContext:
        if session.client_id not in self._contexts:
            self._contexts[session.client_id] = StateContext()
        return self._contexts[session.client_id]

    def _clear_context(self, session: "Session"):
        self._contexts.pop(session.client_id, None)

    # ── Entry Points ──────────────────────────────────────────────────────────

    async def enter_mode_1(self, session: "Session"):
        ctx = self._get_context(session)
        ctx.mode = Mode.MODE_1
        ctx.state = State.STATE_1
        ctx.current_trip_id = self.utility_service.current_trip_id  
        ctx.retry_count = 0
        logger.info(
            "State machine: entered MODE_1 → STATE_1 client_id=%s trip_id=%s",
            session.client_id, ctx.current_trip_id,
        )

    async def exit_to_mode_0(self, session: "Session"):
        ctx = self._get_context(session)
        ctx.reset()
        logger.info("State machine: exited to MODE_0 client_id=%s", session.client_id)

    # ── ProcessResult ─────────────────────────────────────────────────────────

    @dataclass
    class ProcessResult:
        should_handle: bool
        tts_response: Optional[str]
        next_state: Optional[State]
        action: Optional[str]
        action_params: dict = field(default_factory=dict)
        interruptible: bool = True
        emit_tts_boundary_emotions: bool = True

    # ── Processing ────────────────────────────────────────────────────────────

    async def process_input(
        self,
        session: "Session",
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        ctx = self._get_context(session)

        if ctx.mode == Mode.MODE_0:
            return self.ProcessResult(
                should_handle=False, tts_response=None, next_state=None, action=None,
            )

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

        logger.warning("Unknown state %s for client_id=%s", ctx.state, session.client_id)
        return await self._trigger_fallback(session, ctx)

    def _contains_any_word(self, text: str, patterns: tuple) -> bool:
        normalized = (text or "").strip().lower()
        if not normalized:
            return False
        for pattern in patterns:
            token = (pattern or "").strip().lower()
            if not token:
                continue
            if re.search(rf"\b{re.escape(token)}\b", normalized):
                return True
        return False

    # ── Announcement Builder (hardcoded) ──────────────────────────────────────

    def _build_announcement(
        self,
        success: bool,
        validated_by_photo: bool = False,
        was_last: bool = False,
    ) -> str:
        cfg = self.config

        if validated_by_photo:
            base = cfg.delivery_validated_tts
        elif success:
            base = cfg.delivery_completed_tts
        else:
            base = cfg.delivery_failed_tts

        current_id = self.utility_service.current_trip_id
        if not current_id:
            return base + cfg.route_finished_tts

        next_trip_info = self.utility_service.get_delivery(current_id)
        next_address = " ".join(next_trip_info.get("address").split()[:2]) if next_trip_info else None
        next_client_name = next_trip_info.get("clientName") if next_trip_info else None
        announcement = base + cfg.next_heading_tts.format(
            address=next_address, client=next_client_name
        )
        if was_last or self.utility_service.is_last_trip():
            announcement += cfg.last_delivery_suffix
        return announcement

    def _log_trip_order_state(self, prefix: str) -> None:
        logger.info(
            "%s current_trip_id=%s trip_order=%s",
            prefix,
            self.utility_service.current_trip_id,
            self.utility_service.trip_order,
        )

    def _advance_trip_if_needed(self, completed_trip_id: Optional[str], context: str) -> None:
        """Advance to the next trip only when UtilityService did not already advance."""
        if completed_trip_id is None:
            return

        current_after_update = self.utility_service.current_trip_id
        if current_after_update == completed_trip_id:
            self._log_trip_order_state(f"BEFORE set_next_trip [{context}]")
            self.utility_service.set_next_trip()
            self._log_trip_order_state(f"AFTER set_next_trip [{context}]")
        else:
            logger.info(
                "SKIP set_next_trip [%s]: current_trip_id already advanced to %s after update",
                context,
                current_after_update,
            )

    # ── State Handlers ────────────────────────────────────────────────────────

    async def _handle_state_1(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        text_lower = transcript.lower().strip()

        confirmed = None
        if self._contains_any_word(text_lower, self.config.yes_patterns):
            confirmed = True
        elif self._contains_any_word(text_lower, self.config.no_patterns):
            confirmed = False

        if confirmed is True:
            logger.info("STATE_1: YES detected client_id=%s", session.client_id)

            if ctx.current_trip_id:
                await self._send_mark_delivered_event(session, ctx.current_trip_id)

            # Capturer is_last AVANT set_next_trip pour avoir le bon statut
            was_last_trip = self.utility_service.is_last_trip()
            self._log_trip_order_state("BEFORE set_next_trip [STATE_1]")
            self.utility_service.set_next_trip()
            self._log_trip_order_state("AFTER set_next_trip [STATE_1]")

            await self._send_outcome_emotions(
                session,
                success=True,
                is_last=was_last_trip,
            )

            announcement = self._build_announcement(success=True, was_last=was_last_trip)

            if self.utility_service.current_trip_id:
                asyncio.create_task(
                    self._trigger_start_navigation_delayed(session, self.utility_service.current_trip_id, delay=3.0)
                )

            return self.ProcessResult(
                should_handle=True,
                tts_response=announcement,
                next_state=State.STATE_5,
                action="update_trip",
                action_params={"status": self.config.success_status},
                interruptible=False,
                emit_tts_boundary_emotions=False,
            )

        if confirmed is False:
            logger.info("STATE_1: NO detected client_id=%s → STATE_2", session.client_id)
            return self.ProcessResult(
                should_handle=True,
                tts_response=self.config.ask_reason_tts,
                next_state=State.STATE_2,
                action=None,
                interruptible=False,
            )

        # Invalid → retry
        ctx.retry_count += 1
        logger.info("STATE_1: invalid input (retry %d) client_id=%s", ctx.retry_count, session.client_id)
        return self.ProcessResult(
            should_handle=True,
            tts_response=self.config.invalid_yes_no_tts,
            next_state=State.STATE_1,
            action=None,
            interruptible=False,
        )

    async def _handle_state_2(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        text_lower = transcript.lower().strip()

        if self.config.list_trigger in text_lower:
            logger.info("STATE_2: list requested client_id=%s", session.client_id)
            list_text = "Failure reasons: " + ", ".join(
                f"{i + 1}. {reason}" for i, reason in enumerate(self.config.reason_list)
            )
            return self.ProcessResult(
                should_handle=True,
                tts_response=list_text,
                next_state=State.STATE_2,
                action=None,
            )

        number = NumberExtractor.extract(text_lower)

        if number is not None:
            if 1 <= number <= len(self.config.reason_list):
                reason_index = number - 1
                reason = self.config.reason_list[reason_index]
                ctx.failure_reason = reason
                ctx.failure_reason_index = reason_index

                logger.info(
                    "STATE_2: reason selected #%d: %s client_id=%s",
                    number, reason, session.client_id,
                )

                # Reason 1 = "Customer not available" → demander photo
                if reason_index == 0:
                    ctx.photo_trip_id = ctx.current_trip_id
                    ctx.photo_delivery_id = ctx.current_trip_id
                    ctx.photo_address = "the delivery location"

                    await self._send_ask_photo_event(session, ctx)

                    return self.ProcessResult(
                        should_handle=True,
                        tts_response=self.config.ask_photo_tts,
                        next_state=State.STATE_6,
                        action=None,
                    )

                # Autres raisons → failure + annonce
                if ctx.current_trip_id:
                    await self._send_mark_failed_event(session, ctx.current_trip_id)

                # Capturer is_last AVANT set_next_trip pour avoir le bon statut
                was_last_trip = self.utility_service.is_last_trip()
                self._log_trip_order_state("BEFORE set_next_trip [STATE_2]")
                self.utility_service.set_next_trip()
                self._log_trip_order_state("AFTER set_next_trip [STATE_2]")

                await self._send_outcome_emotions(
                    session,
                    success=False,
                    is_last=was_last_trip,
                )

                announcement = self._build_announcement(success=False, was_last=was_last_trip)

                if self.utility_service.current_trip_id:
                    asyncio.create_task(
                        self._trigger_start_navigation_delayed(session,self.utility_service.current_trip_id, delay=3.0)
                    )

                return self.ProcessResult(
                    should_handle=True,
                    tts_response=announcement,
                    next_state=State.STATE_5,
                    action="update_trip",
                    action_params={
                        "status": self.config.failure_status,
                        "cause": number,
                        "reason": reason,
                    },
                    interruptible=False,
                    emit_tts_boundary_emotions=False,
                )
            else:
                ctx.retry_count += 1
                logger.info(
                    "STATE_2: invalid number (retry %d) client_id=%s",
                    ctx.retry_count, session.client_id,
                )
                return self.ProcessResult(
                    should_handle=True,
                    tts_response=self.config.invalid_number_tts,
                    next_state=State.STATE_2,
                    action=None,
                )

        # Pas de nombre
        ctx.retry_count += 1
        logger.info(
            "STATE_2: no number detected (retry %d) client_id=%s",
            ctx.retry_count, session.client_id,
        )
        return self.ProcessResult(
            should_handle=True,
            tts_response=self.config.retry_tts,
            next_state=State.STATE_2,
            action=None,
        )

    async def _handle_state_4(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        logger.info("STATE_4: trip updated client_id=%s → STATE_5", session.client_id)
        return self.ProcessResult(
            should_handle=True, tts_response=None, next_state=State.STATE_5, action=None,
        )

    async def _handle_state_5(
        self,
        session: "Session",
        ctx: StateContext,
        transcript: str,
    ) -> "DeliveryStateMachine.ProcessResult":
        logger.info("STATE_5: exiting to MODE_0 client_id=%s", session.client_id)
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
        logger.info(
            "STATE_6: ignoring transcript while waiting photo event client_id=%s transcript=%r",
            session.client_id, transcript,
        )
        return self.ProcessResult(
            should_handle=True,
            tts_response=None,
            next_state=State.STATE_6,
            action=None,
            interruptible=False,
        )

    # ── Photo Response ────────────────────────────────────────────────────────

    async def handle_photo_response(
        self,
        session: "Session",
        photo_taken: bool,
    ) -> None:
        logger.info(
            "📸 Photo response received client_id=%s photo_taken=%s",
            session.client_id, photo_taken,
        )
        ctx = self._get_context(session)

        if photo_taken:
            trip_id = ctx.photo_trip_id or ctx.current_trip_id
            if trip_id:
                await self.update_trip_status(
                    driver_serial=session.driver_serial,
                    trip_id=trip_id,
                    status="COMPLETED",
                )
                self.utility_service.set_delivery_status(trip_id, "COMPLETED")
                await self._send_mark_delivered_event(session, trip_id)
                

            was_last_trip = self.utility_service.is_last_trip()
            self._advance_trip_if_needed(trip_id, "PHOTO_RESPONSE: success")

            await self._announce_next_trip_and_start_navigation(
                session, success=True, validated_by_photo=True, was_last=was_last_trip,
            )
        else:
            trip_id = ctx.photo_trip_id or ctx.current_trip_id
            reason = ctx.failure_reason or "Other"
            if trip_id:
                await self.update_trip_status(
                    driver_serial=session.driver_serial,
                    trip_id=trip_id,
                    status="FAILED",
                    cause=(ctx.failure_reason_index + 1) if ctx.failure_reason_index is not None else None,
                    reason=reason,
                )
                self.utility_service.set_delivery_status(trip_id, "FAILED")
                await self._send_mark_failed_event(session, trip_id)

            was_last_trip = self.utility_service.is_last_trip()
            self._advance_trip_if_needed(trip_id, "PHOTO_RESPONSE: failure")

            await self._announce_next_trip_and_start_navigation(session, success=False, was_last=was_last_trip)

        ctx.reset()

    async def _announce_next_trip_and_start_navigation(
        self,
        session: "Session",
        success: bool,
        validated_by_photo: bool = False,
        was_last: bool = False,
    ) -> None:
        await self._send_outcome_emotions(
            session,
            success=success,
            is_last=was_last,
        )

        announcement = self._build_announcement(
            success=success,
            validated_by_photo=validated_by_photo,
            was_last=was_last,
        )

        logger.info("📢 Announcement client_id=%s: %s", session.client_id, announcement)

        if self._agent_service:
            await self._agent_service.speak_text(session, announcement)

        if self.utility_service.current_trip_id:
            asyncio.create_task(
                self._trigger_start_navigation_delayed(session, self.utility_service.current_trip_id, delay=3.0)
            )

    # ── Events ────────────────────────────────────────────────────────────────

    async def _send_ask_photo_event(self, session: "Session", ctx: StateContext) -> None:
        if self._ws_service is None:
            logger.warning("WebSocketService not available for ask_photo_event")
            return
        from datetime import datetime
        event = {
            "type": "ask_photo_event",
            "trip_id": ctx.photo_trip_id or ctx.current_trip_id,
            "delivery_id": ctx.photo_delivery_id or ctx.current_trip_id,
            "address": ctx.photo_address or "unknown",
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            await self._ws_service.send(session, event)
            logger.info("📸 ask_photo_event sent client_id=%s", session.client_id)
        except Exception as e:
            logger.error("Error sending ask_photo_event: %s", e)

    async def _send_emotion(self, session: "Session", name: str) -> None:
        if self._ws_service is None:
            return
        try:
            await self._ws_service.send(session, {"type": "emotion", "name": name})
            logger.info("😊 Emotion sent client_id=%s name=%s", session.client_id, name)
        except Exception as e:
            logger.error("Error sending emotion: %s", e)

    async def _send_outcome_emotions(
        self, session: "Session", *, success: bool, is_last: bool = False,
    ) -> None:
        if is_last:
            await self._send_emotion(session, "end")
            return
        await self._send_emotion(session, "happy" if success else "sad")
        
    async def _send_mark_delivered_event(self, session: "Session", trip_id: str) -> None:
        if self._ws_service is None:
            return
        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.MARK_DELIVERED",
            "extras": {"com.avvc.maps.extra.DESTINATION_ID": trip_id},
        }
        try:
            await self._ws_service.send(session, event)
            logger.info("📍 MARK_DELIVERED sent client_id=%s trip_id=%s", session.client_id, trip_id)
        except Exception as e:
            logger.error("Error sending MARK_DELIVERED: %s", e)

    async def _send_mark_failed_event(self, session: "Session", trip_id: str) -> None:
        if self._ws_service is None:
            return
        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.MARK_FAILED",
            "extras": {"com.avvc.maps.extra.DESTINATION_ID": trip_id},
        }
        try:
            await self._ws_service.send(session, event)
            logger.info("❌ MARK_FAILED sent client_id=%s trip_id=%s", session.client_id, trip_id)
        except Exception as e:
            logger.error("Error sending MARK_FAILED: %s", e)

    # ── Navigation ────────────────────────────────────────────────────────────

    async def _trigger_start_navigation(self, session: "Session", trip_id: str) -> None:
        if self._ws_service is None:
            return
        event = {
            "type": "external_control",
            "action": "com.avvc.maps.action.START_NAVIGATION",
            "extras": {"id": trip_id},
        }
        try:
            await self._ws_service.send(session, event)
            logger.info("🗺️ start_navigation sent client_id=%s trip_id=%s", session.client_id, trip_id)
        except Exception as e:
            logger.error("Error sending start_navigation: %s", e)

    async def _trigger_start_navigation_delayed(
        self, session: "Session", trip_id: str, delay: float = 3.0,
    ) -> None:
        await asyncio.sleep(delay)
        await self._trigger_start_navigation(session, trip_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _trigger_fallback(
        self, session: "Session", ctx: StateContext,
    ) -> "DeliveryStateMachine.ProcessResult":
        ctx.reset()
        ctx.mode = Mode.MODE_1
        ctx.state = State.STATE_1
        fallback_message = f"{self.config.fallback_tts} {self.config.ask_completion_tts}"
        return self.ProcessResult(
            should_handle=True,
            tts_response=fallback_message,
            next_state=State.STATE_1,
            action=None,
        )

    # ── Planning Service ──────────────────────────────────────────────────────

    async def update_trip_status(
        self,
        driver_serial: str,
        trip_id: str,
        status: str,
        cause: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> bool:
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent / "data_base_service"))
        try:
            from services.data_base_service.service.planning_service import PlanningService
            from services.data_base_service.service import TokenManager
            from services.data_base_service.entities.enum.package_status import PackageStatus

            script_dir = Path(__file__).parent.parent / "data_base_service"
            token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
            planning_service = PlanningService(token_manager)

            try:
                if status == "COMPLETED":
                    package_status = PackageStatus.DELIVERED_SUCCESSFULLY
                    print(self.utility_service.set_delivery_status(trip_id, "COMPLETED"))
                elif status == "FAILED":
                    package_status = PackageStatus.DELIVERY_FAILURE
                    print(self.utility_service.set_delivery_status(trip_id, "FAILED"))
                else:
                    package_status = PackageStatus.PLANNED

                result = await planning_service.update_package_status(
                    package_id=trip_id, new_status=package_status,
                )

                if status == "FAILED" and reason and result:
                    failure_cause = cause or self._resolve_failure_cause(reason)
                    await planning_service.add_delivery_failure(
                        package_id=trip_id, cause=failure_cause, comment=reason,
                    )

                logger.info(
                    "Package %s updated: status=%s, reason=%s",
                    trip_id, status, reason or "N/A",
                )
                return result
            finally:
                await planning_service.close()

        except Exception as e:
            logger.exception("Failed to update trip status: %s", e)
            return False

    def _resolve_failure_cause(self, reason: str) -> int:
        number = NumberExtractor.extract(reason)
        if number is not None and 1 <= number <= len(self.config.reason_list):
            return number
        normalized_reason = reason.strip().lower()
        for index, label in enumerate(self.config.reason_list, start=1):
            if normalized_reason == label.lower():
                return index
        return len(self.config.reason_list)

    # ── Session Management ────────────────────────────────────────────────────

    def get_session_state(self, session: "Session") -> tuple[Mode, State]:
        ctx = self._get_context(session)
        return ctx.mode, ctx.state

    def is_in_mode_1(self, session: "Session") -> bool:
        ctx = self._get_context(session)
        return ctx.mode == Mode.MODE_1