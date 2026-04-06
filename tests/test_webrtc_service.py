import asyncio
import numpy as np
import pytest
from unittest.mock import MagicMock

from models.session import Session
from services.audio_service import AudioService
from services.vad_service import VADService
from services.webrtc_service import MediaStreamError, TTSAudioTrack, WebRTCService
import config


# Sample rate utilisé par TTSAudioTrack (AUDIO_OUTPUT_SAMPLE_RATE ou SAMPLE_RATE)
TTS_SAMPLE_RATE = getattr(config, "AUDIO_OUTPUT_SAMPLE_RATE", config.SAMPLE_RATE)
FRAME_SAMPLES = int(TTS_SAMPLE_RATE * 0.02)  # 20ms de samples


@pytest.mark.asyncio
async def test_tts_audio_track_sends_frames_immediately():
    """Le track envoie les frames immédiatement sans prebuffer."""
    audio = AudioService()
    track = TTSAudioTrack()

    # Envoyer un frame
    frame = audio.array_to_av_frame(np.ones(FRAME_SAMPLES, dtype=np.float32), TTS_SAMPLE_RATE)
    await track.feed(frame)

    # Le frame doit être reçu immédiatement
    out = await track.recv()
    assert out.samples == FRAME_SAMPLES


@pytest.mark.asyncio
async def test_tts_audio_track_returns_silence_on_timeout():
    """Après timeout, le track retourne un frame de silence."""
    track = TTSAudioTrack()
    track._queue_timeout_sec = 0.01  # Très court pour le test

    # Pas de frame dans la queue → silence après timeout
    silence = await track.recv()
    assert silence.samples == FRAME_SAMPLES


@pytest.mark.asyncio
async def test_tts_audio_track_clear_empties_queue():
    """clear() vide la queue."""
    audio = AudioService()
    track = TTSAudioTrack()

    # Ajouter des frames
    for _ in range(3):
        frame = audio.array_to_av_frame(np.ones(FRAME_SAMPLES, dtype=np.float32), TTS_SAMPLE_RATE)
        await track.feed(frame)

    # Vider
    await track.clear()

    # La queue doit être vide
    assert track._queue.empty()


class _FakeTrack:
    kind = "audio"

    def __init__(self, frames):
        self._frames = iter(frames)

    async def recv(self):
        try:
            return next(self._frames)
        except StopIteration as exc:
            raise MediaStreamError from exc


@pytest.mark.asyncio
async def test_process_audio_track_does_not_duplicate_vad_pre_roll():
    """Le pré-roll 16k doit rester piloté par le VAD, sans doublons côté WebRTC."""
    audio = AudioService()
    vad = VADService()
    vad._model = MagicMock(return_value=0.1)
    vad._chunk_samples = 512
    vad._silence_threshold = 15
    vad._min_speech_chunks = 10
    vad._start_trigger_chunks = 2
    vad._pre_roll_chunks = 2
    vad._post_roll_chunks = 2

    agent = MagicMock()
    agent.denoise = None

    service = WebRTCService(vad=vad, agent=agent, audio=audio, ws=None)
    session = Session(client_id="test-client", websocket=MagicMock())

    chunk_a = np.ones(512, dtype=np.float32) * 0.25
    chunk_b = np.ones(512, dtype=np.float32) * -0.5
    frames = [
        audio.array_to_av_frame(chunk_a, config.SAMPLE_RATE),
        audio.array_to_av_frame(chunk_b, config.SAMPLE_RATE),
    ]

    await service._process_audio_track(session, _FakeTrack(frames))

    assert len(session.pre_speech_buffer) == 2
    np.testing.assert_allclose(session.pre_speech_buffer[0], chunk_a, atol=5e-5)
    np.testing.assert_allclose(session.pre_speech_buffer[1], chunk_b, atol=5e-5)
