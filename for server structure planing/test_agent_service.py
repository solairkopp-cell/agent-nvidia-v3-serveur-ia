"""
tests/test_agent_service.py
Tests unitaires de l'AgentService.
STT, LLM et TTS sont mockés.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from models.session import Session
from services.agent_service import AgentService
from services.whisper_service import TranscriptionResult


@pytest.fixture
def session():
    ws_mock = MagicMock()
    s = Session(client_id="test-client", websocket=ws_mock)
    s.tts_track = AsyncMock()
    s.tts_track.clear = AsyncMock()
    s.tts_track.feed = AsyncMock()
    return s


@pytest.fixture
def agent():
    stt = AsyncMock()
    llm = AsyncMock()
    tts = AsyncMock()
    audio = MagicMock()
    return AgentService(stt=stt, llm=llm, tts=tts, audio=audio)


class TestProcessUtterance:

    @pytest.mark.asyncio
    async def test_empty_transcript_skipped(self, agent, session):
        """Si STT retourne vide → pas d'appel LLM."""
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="")
        )
        await agent.process_utterance(session, b"wav_bytes")
        agent.llm.generate_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_transcript_added_to_history(self, agent, session):
        """Le transcript est ajouté à l'historique de conversation."""
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        # Simuler _stream_response qui retourne une réponse vide
        agent._stream_response = AsyncMock(return_value="hi")

        await agent.process_utterance(session, b"wav_bytes")

        assert any(
            m["role"] == "user" and m["content"] == "hello"
            for m in session.conversation_history
        )

    @pytest.mark.asyncio
    async def test_response_added_to_history(self, agent, session):
        """La réponse LLM est ajoutée à l'historique."""
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        agent._stream_response = AsyncMock(return_value="hi there")

        await agent.process_utterance(session, b"wav_bytes")

        assert any(
            m["role"] == "assistant" and m["content"] == "hi there"
            for m in session.conversation_history
        )

    @pytest.mark.asyncio
    async def test_cancel_flag_stops_processing(self, agent, session):
        """Si cancel_flag est True → pas de traitement."""
        session.cancel_flag = True
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        await agent.process_utterance(session, b"wav_bytes")
        agent.stt.transcribe.assert_not_called()


class TestInterrupt:

    @pytest.mark.asyncio
    async def test_interrupt_sets_cancel_flag(self, agent, session):
        """interrupt() met cancel_flag à True."""
        session.cancel_flag = False
        await agent.interrupt(session)
        assert session.cancel_flag is True

    @pytest.mark.asyncio
    async def test_interrupt_clears_tts_track(self, agent, session):
        """interrupt() vide la queue du TTSAudioTrack."""
        await agent.interrupt(session)
        session.tts_track.clear.assert_called_once()
