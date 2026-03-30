import asyncio
import numpy as np
import pytest
from unittest.mock import patch

from services.audio_service import AudioService
from services.webrtc_service import TTSAudioTrack
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
