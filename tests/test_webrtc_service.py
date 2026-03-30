import asyncio
import numpy as np
import pytest
from unittest.mock import patch

from services.audio_service import AudioService
from services.webrtc_service import TTSAudioTrack


@pytest.mark.asyncio
async def test_tts_audio_track_primes_prebuffer_before_playback():
    audio = AudioService()

    with patch("config.TTS_PLAYBACK_PREBUFFER_MS", 60):
        track = TTSAudioTrack()

    frames = audio.array_to_av_frames(
        np.ones(960, dtype=np.float32),
        source_rate=16000,
        target_rate=16000,
        frame_ms=20,
    )
    for frame in frames[:3]:
        await track.feed(frame)

    out = await track.recv()

    assert out.samples == 320
    assert track._started is True
    assert len(track._staged) == 2


@pytest.mark.asyncio
async def test_tts_audio_track_rearms_prebuffer_after_underrun():
    audio = AudioService()

    with patch("config.TTS_PLAYBACK_PREBUFFER_MS", 40):
        track = TTSAudioTrack()

    track._queue_timeout_sec = 0.01
    await track.feed(audio.array_to_av_frame(np.ones(320, dtype=np.float32), 16000))

    first = await track.recv()
    silence = await track.recv()

    assert first.samples == 320
    assert silence.samples == 320
    assert track._started is False


@pytest.mark.asyncio
async def test_tts_audio_track_reports_buffered_ms_and_waits_for_drain():
    audio = AudioService()

    with patch("config.TTS_PLAYBACK_PREBUFFER_MS", 0):
        track = TTSAudioTrack()

    frame = audio.array_to_av_frame(np.ones(320, dtype=np.float32), 16000)
    await track.feed(frame)

    assert track.buffered_ms() == pytest.approx(20.0, abs=1e-6)

    waiter = asyncio.create_task(track.wait_until_buffer_below(0))
    await asyncio.sleep(0)
    assert waiter.done() is False

    out = await track.recv()
    await waiter

    assert out.samples == 320
    assert track.buffered_ms() == pytest.approx(0.0, abs=1e-6)
