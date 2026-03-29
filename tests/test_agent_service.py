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
    denoise = MagicMock()
    denoise.process_utterance = AsyncMock()
    return AgentService(stt=stt, llm=llm, tts=tts, audio=audio, denoise=denoise)


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
    async def test_intent_event_sent_to_client_even_when_unknown(self, agent, session):
        """Le client reçoit toujours le résultat d'intent, y compris INCONNU."""
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        agent._stream_response = AsyncMock(return_value="")
        agent.intent = MagicMock()
        agent.intent.getint = MagicMock(return_value="INCONNU")
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_transcript = AsyncMock()

        await agent.process_utterance(session, b"wav_bytes")

        agent.ws_service.send_transcript.assert_awaited_once_with(session, "hello")
        agent.ws_service.send.assert_awaited_once_with(
            session,
            {"type": "intent", "intent": "INCONNU"},
        )

    @pytest.mark.asyncio
    async def test_stale_cancel_flag_does_not_block_next_processing(self, agent, session):
        """Un cancel_flag ancien ne doit pas bloquer la prochaine utterance."""
        session.cancel_flag = True
        agent.audio.normalize = MagicMock(side_effect=lambda x: x)
        agent.stt.transcribe_pcm = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        agent._stream_response = AsyncMock(return_value="")

        await agent.process_utterance_pcm(session, np.ones(1600, dtype=np.float32), 16000)

        agent.stt.transcribe_pcm.assert_awaited_once()
        assert session.cancel_flag is False

    @pytest.mark.asyncio
    async def test_pcm_transcription_uses_raw_audio_when_stt_denoise_disabled(self, agent, session, monkeypatch):
        monkeypatch.setattr("config.DENOISE_FOR_STT", False)
        agent.audio.normalize = MagicMock(side_effect=lambda x: x)
        agent.stt.transcribe_pcm = AsyncMock(return_value=TranscriptionResult(text="hello"))
        agent._stream_response = AsyncMock(return_value="")
        samples = np.ones(1600, dtype=np.float32)

        await agent.process_utterance_pcm(session, samples, 16000)

        agent.denoise.process_utterance.assert_not_awaited()
        stt_samples = agent.stt.transcribe_pcm.await_args.args[0]
        np.testing.assert_array_equal(stt_samples, samples)

    @pytest.mark.asyncio
    async def test_pcm_transcription_can_use_denoised_audio_for_stt(self, agent, session, monkeypatch):
        monkeypatch.setattr("config.DENOISE_FOR_STT", True)
        denoised = np.full(1600, 0.25, dtype=np.float32)
        agent.audio.normalize = MagicMock(side_effect=lambda x: x)
        agent.denoise.process_utterance = AsyncMock(return_value=denoised)
        agent.stt.transcribe_pcm = AsyncMock(return_value=TranscriptionResult(text="hello"))
        agent._stream_response = AsyncMock(return_value="")

        await agent.process_utterance_pcm(session, np.ones(1600, dtype=np.float32), 16000)

        agent.denoise.process_utterance.assert_awaited_once()
        stt_samples = agent.stt.transcribe_pcm.await_args.args[0]
        np.testing.assert_array_equal(stt_samples, denoised)


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


class TestStreamResponse:

    @pytest.mark.asyncio
    async def test_stream_response_sends_all_audio_frames(self, agent, session):
        """Le flux TTS est découpé en frames et poussé intégralement vers la track."""

        async def fake_token_stream():
            yield "Bonjour."

        async def fake_tts_stream(_text_stream, cancel_check=None):
            yield ("Bonjour.", np.ones(24000, dtype=np.float32), 24000)

        agent.llm.generate_stream = MagicMock(return_value=fake_token_stream())
        agent.tts.synthesize_stream = fake_tts_stream
        agent.audio.array_to_av_frames = MagicMock(return_value=["frame-1", "frame-2", "frame-3"])
        agent.ws_service = MagicMock()
        agent.ws_service.send_response_chunk = AsyncMock()

        reply = await agent._stream_response(session, "hello", request_id=session.current_request_id)

        assert reply == "Bonjour."
        agent.audio.array_to_av_frames.assert_called_once()
        assert session.tts_track.feed.await_count == 3
        session.tts_track.feed.assert_any_await("frame-1")
        session.tts_track.feed.assert_any_await("frame-2")
        session.tts_track.feed.assert_any_await("frame-3")
        agent.ws_service.send_response_chunk.assert_awaited_once_with(session, "Bonjour.")
