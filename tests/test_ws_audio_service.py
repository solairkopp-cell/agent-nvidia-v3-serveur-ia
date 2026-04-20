import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

import config
from models.session import Session
from services.audio_service import AudioService
from services.vad_service import VADService
from services.ws_audio_service import AudioSocketOutput, WebSocketAudioService


@pytest.mark.asyncio
async def test_websocket_audio_output_sends_pcm16_bytes():
    audio = AudioService()
    websocket = MagicMock()
    websocket.send_bytes = AsyncMock()
    session = Session(client_id="test-client", websocket=websocket)

    output = AudioSocketOutput(session, audio, sample_rate=48000)
    await output.feed(np.ones(960, dtype=np.float32) * 0.5)

    websocket.send_bytes.assert_awaited_once()
    payload = websocket.send_bytes.await_args.args[0]
    assert isinstance(payload, bytes)
    assert len(payload) == 960 * 2


@pytest.mark.asyncio
async def test_handle_audio_bytes_does_not_duplicate_vad_pre_roll():
    audio = AudioService()
    vad = VADService()
    vad._model = MagicMock(return_value=0.1)
    vad._chunk_samples = 512
    vad._silence_threshold = 15
    vad._min_speech_chunks = 10
    vad._start_trigger_chunks = 2
    vad._pre_roll_chunks = 2
    vad._post_roll_chunks = 2

    websocket = MagicMock()
    websocket.send_json = AsyncMock()
    websocket.send_bytes = AsyncMock()
    session = Session(client_id="test-client", websocket=websocket)

    agent = MagicMock()
    agent.denoise = None
    agent.on_user_speech_start = AsyncMock()

    service = WebSocketAudioService(vad=vad, agent=agent, audio=audio, ws=None)
    await service.start_session(session, input_sample_rate=config.SAMPLE_RATE)

    chunk_a = np.ones(512, dtype=np.float32) * 0.25
    chunk_b = np.ones(512, dtype=np.float32) * -0.5
    payload = audio.array_to_pcm16_bytes(np.concatenate([chunk_a, chunk_b]))

    await service.handle_audio_bytes(session, payload)

    assert len(session.pre_speech_buffer) == 2
    np.testing.assert_allclose(session.pre_speech_buffer[0], chunk_a, atol=5e-5)
    np.testing.assert_allclose(session.pre_speech_buffer[1], chunk_b, atol=5e-5)
