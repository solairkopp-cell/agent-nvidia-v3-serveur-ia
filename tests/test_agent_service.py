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
    s.tts_track.wait_until_buffer_below = AsyncMock()
    return s


@pytest.fixture
def agent():
    stt = AsyncMock()
    llm = AsyncMock()
    tts = AsyncMock()
    audio = MagicMock()
    audio.trim_silence = MagicMock(side_effect=lambda samples, **kwargs: samples)
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
        agent.llm.chat.assert_not_called()

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
    async def test_transcript_event_sent_to_client(self, agent, session):
        agent.stt.transcribe = AsyncMock(
            return_value=TranscriptionResult(text="hello")
        )
        agent._stream_response = AsyncMock(return_value="")
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_transcript = AsyncMock()

        await agent.process_utterance(session, b"wav_bytes")

        agent.ws_service.send_transcript.assert_awaited_once_with(session, "hello")
        agent.ws_service.send.assert_not_awaited()

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

    @pytest.mark.asyncio
    async def test_effective_transcript_is_forwarded_to_stream_response(self, agent, session):
        agent.stt.transcribe = AsyncMock(return_value=TranscriptionResult(text="who is next"))
        agent._stream_response = AsyncMock(return_value="Alice")

        await agent.process_utterance(session, b"wav_bytes")

        kwargs = agent._stream_response.await_args.kwargs
        assert kwargs["user_text"] == "who is next"


class TestInterrupt:

    @pytest.mark.asyncio
    async def test_interrupt_sets_cancel_flag(self, agent, session):
        """interrupt() met cancel_flag à True."""
        session.cancel_flag = False
        await agent.interrupt(session)
        assert session.cancel_flag is True

    @pytest.mark.asyncio
    async def test_interrupt_clears_tts_track(self, agent, session):
        """interrupt() vide la sortie audio en cours."""
        await agent.interrupt(session)
        session.tts_track.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_user_speech_start_stops_tts_immediately(self, agent, session):
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        session.tts_playing = True
        session.tts_started_at = 1.0

        with patch("time.monotonic", return_value=1.4):
            await agent.on_user_speech_start(session)

        assert session.interruption_pending is True
        assert session.interruption_elapsed_ms == pytest.approx(400.0, abs=1e-6)
        session.tts_track.clear.assert_awaited_once()
        agent.ws_service.send.assert_awaited_once_with(session, {"type": "tts_stop_now"})


class TestTranscriptionInterruption:

    @pytest.mark.asyncio
    async def test_process_transcription_continuation_merges_active_user_turn(self, agent, session):
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_transcript = AsyncMock()
        agent._stream_response = AsyncMock(return_value="")
        session.conversation_history = [{"role": "user", "content": "hello"}]
        session.mark_active_user_turn(request_id=1, index=0, text="hello")
        session.current_request_id = 2
        session.interruption_pending = True
        session.interruption_elapsed_ms = 200.0

        await agent._process_transcription(session, 2, "there")

        assert session.conversation_history == [{"role": "user", "content": "hello there"}]
        kwargs = agent._stream_response.await_args.kwargs
        assert kwargs["session"] is session
        assert kwargs["user_text"] == "hello there"
        assert kwargs["request_id"] == 2
        assert session.active_user_message_index is None

    @pytest.mark.asyncio
    async def test_process_transcription_interruption_replaces_active_user_turn(self, agent, session):
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_transcript = AsyncMock()
        agent._stream_response = AsyncMock(return_value="")
        session.conversation_history = [{"role": "user", "content": "hello"}]
        session.mark_active_user_turn(request_id=1, index=0, text="hello")
        session.current_request_id = 2
        session.interruption_pending = True
        session.interruption_elapsed_ms = 1400.0

        await agent._process_transcription(session, 2, "new request")

        assert session.conversation_history == [{"role": "user", "content": "new request"}]
        kwargs = agent._stream_response.await_args.kwargs
        assert kwargs["session"] is session
        assert kwargs["user_text"] == "new request"
        assert kwargs["request_id"] == 2
        assert session.active_user_message_index is None

    def test_decide_interruption_mode_uses_configured_thresholds_and_words(self, agent, session):
        session.interruption_elapsed_ms = 200.0

        with (
            patch("config.INTERRUPTION_SHORT_THRESHOLD_MS", 250.0),
            patch("config.INTERRUPTION_WORDS_EN", ("halt", "cancel that")),
            patch("config.CONTINUATION_WORDS_EN", ("carry on", "also")),
        ):
            assert agent._decide_interruption_mode(session, "carry on please") == "continuation"
            assert agent._decide_interruption_mode(session, "halt now") == "interruption"

        session.interruption_elapsed_ms = 400.0
        with (
            patch("config.INTERRUPTION_SHORT_THRESHOLD_MS", 250.0),
            patch("config.INTERRUPTION_WORDS_EN", ("halt",)),
            patch("config.CONTINUATION_WORDS_EN", ("carry on",)),
        ):
            assert agent._decide_interruption_mode(session, "neutral words only") == "interruption"


class TestStreamResponse:

    @pytest.mark.asyncio
    async def test_stream_response_uses_llm_streaming_when_available(self, agent, session, monkeypatch):
        monkeypatch.setattr("config.OLLAMA_STREAM", True)

        async def fake_stream_chat(user_message, history=None, session=None):
            yield "Bonjour."
            yield " Encore."

        async def fake_tts_stream(text_stream, cancel_check=None):
            async for chunk in text_stream:
                phrase = chunk.strip()
                if phrase:
                    yield (phrase, np.ones(960, dtype=np.float32), 48000)

        agent.llm.stream_chat = fake_stream_chat
        agent.llm.chat = AsyncMock(return_value="fallback")
        agent.tts.synthesize_stream = fake_tts_stream
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_response_chunk = AsyncMock()

        reply = await agent._stream_response(session, "hello", request_id=session.current_request_id)

        assert reply == "Bonjour. Encore."
        agent.llm.chat.assert_not_awaited()
        assert session.tts_track.feed.await_count >= 1
        sent_chunks = [call.args[1] for call in agent.ws_service.send_response_chunk.await_args_list]
        assert sent_chunks == ["Bonjour.", "Encore."]

    @pytest.mark.asyncio
    async def test_stream_response_sends_all_audio_frames(self, agent, session):
        """Le flux TTS est découpé en frames et poussé intégralement vers la track."""
        with patch("config.TTS_SEGMENT_OVERLAP_MS", 0):
            agent.llm.chat = AsyncMock(return_value="Bonjour.")
            agent.tts.synthesize = AsyncMock(return_value=(np.ones(4800, dtype=np.float32), 48000))
            agent.ws_service = MagicMock()
            agent.ws_service.send = AsyncMock()
            agent.ws_service.send_response_chunk = AsyncMock()

            reply = await agent._stream_response(session, "hello", request_id=session.current_request_id)

            assert reply == "Bonjour."
            assert session.tts_track.feed.await_count >= 1
            agent.ws_service.send_response_chunk.assert_awaited_once_with(session, "Bonjour.")

    @pytest.mark.asyncio
    async def test_speak_text_streams_audio_and_sends_tts_test_event(self, agent, session):
        async def fake_tts_stream(_text_stream, cancel_check=None):
            yield ("Test audio.", np.ones(16000, dtype=np.float32), 16000)

        agent.tts.synthesize_stream = fake_tts_stream
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()

        await agent.speak_text(session, "Test audio.")

        sent_payloads = [call.args[1] for call in agent.ws_service.send.await_args_list]
        assert {"type": "tts_test", "text": "Test audio."} in sent_payloads
        assert session.tts_track.feed.await_count >= 1

    @pytest.mark.asyncio
    async def test_stream_response_sends_all_frames(self, agent, session):
        """Le stream response envoie tous les frames TTS."""
        agent.llm.chat = AsyncMock(return_value="Bonjour. Encore.")
        agent.tts.synthesize = AsyncMock(return_value=(np.ones(2880, dtype=np.float32), 48000))
        agent.ws_service = MagicMock()
        agent.ws_service.send = AsyncMock()
        agent.ws_service.send_response_chunk = AsyncMock()

        await agent._stream_response(session, "hello", request_id=session.current_request_id)

        # Les frames sont envoyés
        assert session.tts_track.feed.await_count >= 1

    def test_prepare_tts_samples_returns_samples_as_is(self, agent, session):
        """_prepare_tts_samples retourne les samples sans overlap."""
        agent.audio.trim_silence = MagicMock(side_effect=lambda samples, **kwargs: samples)

        samples = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
        out = agent._prepare_tts_samples(session, samples, 1000)

        np.testing.assert_array_equal(out, samples)
