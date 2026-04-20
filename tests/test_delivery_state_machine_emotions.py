from unittest.mock import AsyncMock, MagicMock, call, patch

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
            "reason": "Wrong address",
        }
        assert result.emit_tts_boundary_emotions is False

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
