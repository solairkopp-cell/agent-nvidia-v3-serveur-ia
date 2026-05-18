import sys
import types
from enum import Enum
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.session import Session
from services.delivery_state_machine import DeliveryStateMachine, Mode, State


@pytest.fixture
def session():
    s = Session(client_id="test-client", websocket=MagicMock())
    s.current_trip_id = "trip-1"
    s.driver_serial = "driver-1"
    return s


@pytest.fixture
def state_machine():
    sm = DeliveryStateMachine()
    sm._send_mark_delivered_event = AsyncMock()
    sm._send_mark_failed_event = AsyncMock()
    sm._send_emotion = AsyncMock()
    return sm


def _enter_mode_1(sm: DeliveryStateMachine, session: Session, state: State) -> None:
    ctx = sm._get_context(session)
    ctx.mode = Mode.MODE_1
    ctx.state = state
    ctx.current_trip_id = session.current_trip_id


class TestDeliveryStateMachineEmotions:

    @pytest.mark.asyncio
    async def test_success_path_sends_happy_without_photo_flow(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_1)
        state_machine._get_next_trip_info = AsyncMock(return_value=None)
        state_machine._should_send_end_emotion = AsyncMock(return_value=False)

        result = await state_machine.process_input(session, "yes")

        state_machine._send_mark_delivered_event.assert_awaited_once_with(session, "trip-1")
        state_machine._send_emotion.assert_awaited_once_with(session, "happy")
        assert result.action == "update_trip"
        assert result.action_params == {"status": "COMPLETED"}
        assert result.emit_tts_boundary_emotions is False
        assert "last delivery" in result.tts_response.lower()

    @pytest.mark.asyncio
    async def test_failure_path_sends_sad_without_photo_flow(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_2)
        state_machine._get_next_trip_info = AsyncMock(return_value=None)
        state_machine._should_send_end_emotion = AsyncMock(return_value=False)

        result = await state_machine.process_input(session, "2")

        state_machine._send_mark_failed_event.assert_awaited_once_with(session, "trip-1")
        state_machine._send_emotion.assert_awaited_once_with(session, "sad")
        assert result.action == "update_trip"
        assert result.action_params == {
            "status": "FAILED",
            "cause": 2,
            "reason": "Wrong address",
        }
        assert result.emit_tts_boundary_emotions is False

    @pytest.mark.asyncio
    async def test_update_trip_status_uses_reason_code_for_delivery_failure(self, state_machine):
        class FakeTokenManager:
            def __init__(self, cache_file=None):
                self.cache_file = cache_file

        class FakePlanningService:
            instance = None

            def __init__(self, token_manager):
                self.token_manager = token_manager
                self.update_package_status = AsyncMock(return_value=True)
                self.add_delivery_failure = AsyncMock(return_value=True)
                self.close = AsyncMock()
                FakePlanningService.instance = self

        class FakePackageStatus(Enum):
            DELIVERED_SUCCESSFULLY = "delivered_successfully"
            DELIVERY_FAILURE = "delivery_failure"
            PLANNED = "planned"

        service_module = types.ModuleType("service")
        service_module.TokenManager = FakeTokenManager

        planning_module = types.ModuleType("service.planning_service")
        planning_module.PlanningService = FakePlanningService

        entities_module = types.ModuleType("entities")
        entities_enum_module = types.ModuleType("entities.enum")
        package_status_module = types.ModuleType("entities.enum.package_status")
        package_status_module.PackageStatus = FakePackageStatus

        with patch.dict(
            sys.modules,
            {
                "service": service_module,
                "service.planning_service": planning_module,
                "entities": entities_module,
                "entities.enum": entities_enum_module,
                "entities.enum.package_status": package_status_module,
            },
        ):
            success = await state_machine.update_trip_status(
                driver_serial="driver-1",
                trip_id="trip-1",
                status="FAILED",
                reason="Wrong address",
            )

        assert success is True
        FakePlanningService.instance.add_delivery_failure.assert_awaited_once_with(
            package_id="trip-1",
            cause=2,
            comment="Wrong address",
        )

    @pytest.mark.asyncio
    async def test_success_path_keeps_end_for_last_upcoming_trip(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_1)
        state_machine._get_next_trip_info = AsyncMock(
            return_value=("trip-2", "123 Main Street", "Alice", True)
        )
        state_machine._should_send_end_emotion = AsyncMock(return_value=True)

        def _fake_create_task(coro):
            coro.close()
            return MagicMock()

        with patch("services.delivery_state_machine.asyncio.create_task", side_effect=_fake_create_task):
            result = await state_machine.process_input(session, "yes")

        state_machine._send_emotion.assert_awaited_once_with(session, "end")
        assert result.emit_tts_boundary_emotions is False
        assert "this is your last delivery" in result.tts_response.lower()

    @pytest.mark.asyncio
    async def test_success_path_sends_end_when_current_trip_is_last(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_1)
        state_machine._get_next_trip_info = AsyncMock(return_value=None)
        state_machine._should_send_end_emotion = AsyncMock(return_value=True)

        result = await state_machine.process_input(session, "yes")

        state_machine._send_emotion.assert_awaited_once_with(session, "end")
        assert result.emit_tts_boundary_emotions is False
        assert "last delivery" in result.tts_response.lower()

    @pytest.mark.asyncio
    async def test_photo_flow_announcements_skip_tts_boundary_emotions(self, state_machine, session):
        state_machine._send_outcome_emotions = AsyncMock()
        state_machine._get_next_trip_info = AsyncMock(return_value=None)
        state_machine._should_send_end_emotion = AsyncMock(return_value=False)
        state_machine._agent_service = MagicMock()
        state_machine._agent_service.speak_text = AsyncMock()

        await state_machine._announce_next_trip_and_start_navigation(session, success=True)

        state_machine._agent_service.speak_text.assert_awaited_once_with(
            session,
            "Delivery completed successfully. It was your last delivery. The route is now finished.",
            interruptible=False,
            emit_boundary_emotions=False,
        )

    @pytest.mark.asyncio
    async def test_photo_flow_announces_next_trip_when_current_trip_exists(self, state_machine, session):
        state_machine._send_outcome_emotions = AsyncMock()
        state_machine._agent_service = MagicMock()
        state_machine._agent_service.speak_text = AsyncMock()
        state_machine.utility_service = MagicMock()
        state_machine.utility_service.current_trip_id = "trip-2"
        state_machine.utility_service.get_delivery.return_value = {
            "address": "123 Main Street",
            "clientName": "Alice",
        }
        state_machine.utility_service.is_last_trip.return_value = True

        await state_machine._announce_next_trip_and_start_navigation(
            session, success=True, validated_by_photo=True, was_last=True
        )

        assert state_machine._agent_service.speak_text.await_count == 1
        actual_call = state_machine._agent_service.speak_text.await_args
        assert actual_call.args == (
            session,
            "Delivery validated. You are now heading to 123 Main. The client is Alice. This is your last delivery.",
        )
        assert actual_call.kwargs == {}

    @pytest.mark.asyncio
    async def test_state_1_uses_llm_confirmation_to_enter_reason_flow(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_1)
        state_machine._agent_service = MagicMock()
        state_machine._agent_service.llm = MagicMock()
        state_machine._agent_service.llm.is_this_a_confirmation = AsyncMock(return_value=False)
        state_machine._agent_service.llm.generate_system_reply = AsyncMock(
            return_value="Please choose a reason from 1 to 6 or ask for the list."
        )

        result = await state_machine.process_input(session, "not completed")

        assert result.next_state == State.STATE_2
        assert result.tts_response == "Please choose a reason from 1 to 6 or ask for the list."
        state_machine._agent_service.llm.is_this_a_confirmation.assert_awaited_once_with(
            "not completed",
            session=session,
        )

    @pytest.mark.asyncio
    async def test_state_2_uses_llm_reason_list_reply(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_2)
        state_machine._agent_service = MagicMock()
        state_machine._agent_service.llm = MagicMock()
        state_machine._agent_service.llm.get_delivery_failure_reason_response = AsyncMock(
            return_value="1. Customer not available, 2. Wrong address"
        )

        result = await state_machine.process_input(session, "give me the list")

        assert result.next_state == State.STATE_2
        assert result.action is None
        assert result.tts_response == "1. Customer not available, 2. Wrong address"

    @pytest.mark.asyncio
    async def test_state_2_uses_llm_reason_number_for_photo_request(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_2)
        state_machine._send_ask_photo_event = AsyncMock()
        state_machine._agent_service = MagicMock()
        state_machine._agent_service.llm = MagicMock()
        state_machine._agent_service.llm.get_delivery_failure_reason_response = AsyncMock(return_value="1")
        state_machine._agent_service.llm.generate_system_reply = AsyncMock(
            return_value="Please take a photo to validate the delivery."
        )

        result = await state_machine.process_input(session, "customer not available")

        assert result.next_state == State.STATE_6
        assert result.tts_response == "Please take a photo to validate the delivery."
        state_machine._send_ask_photo_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_photo_response_customer_not_available_marks_success_when_photo_taken(self, state_machine, session):
        # Simulate that the driver selected reason #1 (Customer not available) but a photo was taken
        _enter_mode_1(state_machine, session, State.STATE_6)
        ctx = state_machine._get_context(session)
        ctx.failure_reason_index = 0
        ctx.failure_reason = "Customer not available"
        ctx.photo_trip_id = "trip-1"
        ctx.current_trip_id = "trip-1"

        # Avoid external DB calls and announcements side-effects
        state_machine.update_trip_status = AsyncMock(return_value=True)
        state_machine._announce_next_trip_and_start_navigation = AsyncMock()
        state_machine.utility_service = MagicMock()
        state_machine.utility_service.is_last_trip.return_value = False
        state_machine.utility_service.set_next_trip = MagicMock()

        await state_machine.handle_photo_response(session, photo_taken=True)

        state_machine.update_trip_status.assert_awaited_once_with(
            driver_serial=session.driver_serial,
            trip_id="trip-1",
            status="COMPLETED",
        )
        state_machine._send_mark_delivered_event.assert_awaited_once_with(session, "trip-1")
        state_machine._send_mark_failed_event.assert_not_awaited()
        state_machine._announce_next_trip_and_start_navigation.assert_awaited_once_with(
            session, success=True, validated_by_photo=True, was_last=False,
        )

    @pytest.mark.asyncio
    async def test_handle_photo_response_skips_set_next_trip_if_current_trip_already_changed(self, state_machine, session):
        _enter_mode_1(state_machine, session, State.STATE_6)
        ctx = state_machine._get_context(session)
        ctx.failure_reason_index = 0
        ctx.failure_reason = "Customer not available"
        ctx.photo_trip_id = "trip-1"
        ctx.current_trip_id = "trip-1"

        state_machine.update_trip_status = AsyncMock(return_value=True)
        state_machine._announce_next_trip_and_start_navigation = AsyncMock()
        state_machine.utility_service = MagicMock()
        state_machine.utility_service.is_last_trip.return_value = False
        state_machine.utility_service.current_trip_id = "trip-2"
        state_machine.utility_service.set_next_trip = MagicMock()

        await state_machine.handle_photo_response(session, photo_taken=True)

        state_machine._send_mark_delivered_event.assert_awaited_once_with(session, "trip-1")
        state_machine.utility_service.set_next_trip.assert_not_called()
        state_machine._announce_next_trip_and_start_navigation.assert_awaited_once_with(
            session, success=True, validated_by_photo=True, was_last=False,
        )
