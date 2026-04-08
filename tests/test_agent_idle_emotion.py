from unittest.mock import AsyncMock, MagicMock, call

import numpy as np
import pytest

from models.session import Session
from services.agent_service import AgentService


@pytest.fixture
def session():
    s = Session(client_id="test-client", websocket=MagicMock())
    s.tts_track = AsyncMock()
    return s


@pytest.fixture
def agent():
    return AgentService(
        stt=AsyncMock(),
        llm=AsyncMock(),
        tts=AsyncMock(),
        audio=MagicMock(),
    )


class TestIdleEmotion:

    @pytest.mark.asyncio
    async def test_speak_text_internal_sends_idle_when_finished(self, agent, session):
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.tts.synthesize_stream = MagicMock(return_value=object())
        agent._play_tts_stream = AsyncMock(return_value=None)

        await agent._speak_text_internal(session, "Bonjour")

        agent.ws_service.send.assert_awaited_once_with(
            session,
            {"type": "emotion", "name": "idle"},
        )

    @pytest.mark.asyncio
    async def test_speak_text_internal_can_skip_boundary_emotions(self, agent, session):
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.tts.synthesize_stream = MagicMock(return_value=object())
        agent._play_tts_stream = AsyncMock(return_value=None)

        await agent._speak_text_internal(session, "Bonjour", emit_boundary_emotions=False)

        agent.ws_service.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stream_response_sends_idle_when_finished(self, agent, session):
        async def fake_token_stream():
            yield "Bonjour."

        agent.llm.generate_stream = MagicMock(return_value=fake_token_stream())
        agent.tts.synthesize = AsyncMock(return_value=(np.ones(960, dtype=np.float32), 48000))
        agent._emit_tts_audio = AsyncMock(return_value=None)
        agent._wait_queue_empty = AsyncMock(return_value=None)
        agent._flush_tts_queue = AsyncMock(return_value=None)
        agent._tts_scheduler = AsyncMock(return_value=None)
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()

        reply = await agent._stream_response(session, "hello", request_id=session.current_request_id)

        assert reply == "Bonjour."
        agent.ws_service.send.assert_has_awaits([
            call(session, {"type": "emotion", "name": "speaking"}),
            call(session, {"type": "emotion", "name": "idle"}),
        ])

    @pytest.mark.asyncio
    async def test_state_response_sends_idle_when_finished(self, agent, session):
        agent.tts.synthesize = AsyncMock(return_value=(np.ones(960, dtype=np.float32), 48000))
        agent._emit_tts_audio = AsyncMock(return_value=None)
        agent._wait_queue_empty = AsyncMock(return_value=None)
        agent._flush_tts_queue = AsyncMock(return_value=None)
        agent._tts_scheduler = AsyncMock(return_value=None)
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()

        await agent._speak_state_response(session, request_id=session.current_request_id, text="Etat")

        agent.ws_service.send.assert_has_awaits([
            call(session, {"type": "emotion", "name": "speaking"}),
            call(session, {"type": "emotion", "name": "idle"}),
        ])

    @pytest.mark.asyncio
    async def test_state_response_can_skip_boundary_emotions(self, agent, session):
        agent.tts.synthesize = AsyncMock(return_value=(np.ones(960, dtype=np.float32), 48000))
        agent._emit_tts_audio = AsyncMock(return_value=None)
        agent._wait_queue_empty = AsyncMock(return_value=None)
        agent._flush_tts_queue = AsyncMock(return_value=None)
        agent._tts_scheduler = AsyncMock(return_value=None)
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()

        await agent._speak_state_response(
            session,
            request_id=session.current_request_id,
            text="Etat",
            emit_boundary_emotions=False,
        )

        agent.ws_service.send.assert_not_awaited()
