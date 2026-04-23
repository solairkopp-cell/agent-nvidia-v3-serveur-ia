"""
services/ws_audio_service.py
Transport audio bidirectionnel via WebSocket binaire.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

import numpy as np

import config
from models.session import Session

if TYPE_CHECKING:
    from services.vad_service import VADService
    from services.agent_service import AgentService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService


logger = logging.getLogger(__name__)


class AudioSocketOutput:
    """
    Adaptateur minimal qui envoie les frames TTS sur le WebSocket.
    """

    def __init__(self, session: Session, audio: "AudioService", sample_rate: int):
        self._session = session
        self._audio = audio
        self._sample_rate = int(sample_rate)

    async def feed(self, samples: np.ndarray) -> None:
        payload = self._audio.array_to_pcm16_bytes(samples)
        if not payload:
            return
        for attempt in range(2):
            try:
                async with self._session.send_lock:
                    await self._session.websocket.send_bytes(payload)
                return
            except Exception:
                if attempt == 0:
                    await asyncio.sleep(0.015)
                    continue
                logger.warning(
                    "Audio chunk send failed (giving up) client_id=%s",
                    self._session.client_id,
                    exc_info=True,
                )

    async def clear(self) -> None:
        return

    async def wait_until_buffer_below(self, _low_watermark_ms: int) -> None:
        return

    def stop(self) -> None:
        return


class WebSocketAudioService:
    """Service de streaming audio via WebSocket."""

    def __init__(
        self,
        vad: "VADService",
        agent: "AgentService",
        audio: "AudioService",
        ws: "WebSocketService | None" = None,
    ):
        self.vad = vad
        self.agent = agent
        self.audio = audio
        self._ws_service = ws

    async def health_check(self) -> bool:
        return True

    async def start_session(self, session: Session, *, input_sample_rate: int | None = None) -> None:
        if isinstance(input_sample_rate, int) and input_sample_rate > 0:
            session.audio_input_sample_rate = int(input_sample_rate)

        output_rate = int(getattr(config, "AUDIO_OUTPUT_SAMPLE_RATE", 48000) or 48000)
        session.audio_output_sample_rate = output_rate
        session.audio_stream_started = True
        session.tts_track = AudioSocketOutput(session, self.audio, output_rate)
        self._reset_input_stream_buffer(session)

        logger.info(
            "Audio WS session started client_id=%s input_sr=%d output_sr=%d",
            session.client_id,
            session.audio_input_sample_rate,
            session.audio_output_sample_rate,
        )

    async def cleanup(self, session: Session) -> None:
        session.audio_stream_started = False
        self._reset_input_stream_buffer(session)

        tts_track = session.tts_track
        session.tts_track = None

        try:
            if tts_track is not None:
                tts_track.stop()
        except Exception:
            logger.debug("Audio output stop failed client_id=%s", session.client_id, exc_info=True)

        session.reset_audio_buffer()
        session.reset_tts_output_state()
        session.tts_playing = False
        logger.info("Audio WS cleaned up client_id=%s", session.client_id)

    async def handle_audio_bytes(self, session: Session, payload: bytes) -> None:
        if not payload or not session.audio_stream_started:
            return

        source_rate = int(session.audio_input_sample_rate or config.SAMPLE_RATE)
        samples = self.audio.pcm_bytes_to_array(payload, dtype="float32")
        if samples.size == 0:
            return

        if source_rate != int(config.SAMPLE_RATE):
            try:
                samples = self.audio.resample(
                    samples,
                    source_rate=source_rate,
                    target_rate=int(config.SAMPLE_RATE),
                )
            except Exception:
                logger.exception(
                    "Input audio resample failed client_id=%s source_sr=%d target_sr=%d",
                    session.client_id,
                    source_rate,
                    int(config.SAMPLE_RATE),
                )
                return

        buffer = getattr(session, "_input_stream_buffer", None)
        if not isinstance(buffer, np.ndarray) or buffer.dtype != np.float32:
            buffer = np.array([], dtype=np.float32)

        if buffer.size == 0:
            buffer = samples.astype(np.float32, copy=False)
        else:
            buffer = np.concatenate([buffer, samples.astype(np.float32, copy=False)])

        chunk_samples = int(config.SAMPLE_RATE * (config.VAD_CHUNK_MS / 1000.0))
        while buffer.size >= chunk_samples and chunk_samples > 0:
            chunk = buffer[:chunk_samples]
            buffer = buffer[chunk_samples:]
            await self._handle_vad_chunk(session, chunk)

        setattr(session, "_input_stream_buffer", buffer.astype(np.float32, copy=False))

    async def _handle_vad_chunk(self, session: Session, chunk: np.ndarray) -> None:
        vad_result = self.vad.process_chunk(session, chunk)

        if vad_result.type == "speech_start":
            logger.info(
                "VAD speech_start client_id=%s p=%.3f",
                session.client_id,
                vad_result.speech_prob,
            )
            try:
                await self.agent.on_user_speech_start(session)
            except Exception:
                logger.exception("Speech-start interruption handling failed client_id=%s", session.client_id)
            await self._send_json(
                session,
                {"type": "vad", "event": "speech_start", "p": vad_result.speech_prob},
            )

        if getattr(vad_result, "ignored_short", False):
            logger.info(
                "VAD short_utterance_ignored client_id=%s speech_chunks=%d",
                session.client_id,
                session.speech_chunks,
            )
            await self._send_json(
                session,
                {"type": "vad", "event": "short_utterance_ignored", "p": vad_result.speech_prob},
            )

        if vad_result.type != "utterance_end" or vad_result.audio is None or vad_result.audio.size == 0:
            return

        logger.info("Utterance end client_id=%s samples=%d", session.client_id, vad_result.audio.size)
        await self._send_json(
            session,
            {"type": "vad", "event": "utterance_end", "samples": int(vad_result.audio.size)},
        )

        if session.processing_lock.locked() and not session.cancel_flag:
            await self.agent.interrupt(session)

        utterance_id = uuid.uuid4().hex[:8]
        asyncio.create_task(
            self.agent.process_utterance_pcm(
                session,
                vad_result.audio,
                int(config.SAMPLE_RATE),
                apply_denoise=getattr(config, "DENOISE_FOR_STT", False),
                utterance_id=utterance_id,
            )
        )

    async def _send_json(self, session: Session, payload: dict) -> None:
        if self._ws_service is not None:
            await self._ws_service.send(session, payload)
            return
        try:
            async with session.send_lock:
                await session.websocket.send_json(payload)
        except Exception:
            logger.debug("WS JSON send failed client_id=%s", session.client_id, exc_info=True)

    def _reset_input_stream_buffer(self, session: Session) -> None:
        setattr(session, "_input_stream_buffer", np.array([], dtype=np.float32))

    async def on_session_ready(self, session: Session) -> None:
        await self._send_pending_voice_summary(session)

    async def _send_pending_voice_summary(self, session: Session) -> None:
        pending_summary = getattr(session, "_pending_voice_summary", None)
        if pending_summary is None:
            return

        logger.info("Sending pending voice summary client_id=%s", session.client_id)
        try:
            trips = pending_summary.get("trips", [])
            driver_name = pending_summary.get("driver_name", "Driver")
            no_trips = pending_summary.get("no_trips", False)
            voice_message = pending_summary.get("voice_message")

            if no_trips and voice_message:
                if self._ws_service is not None:
                    await self._ws_service.send(session, {"type": "emotion", "name": "greeting"})
                await self.agent.speak_text(session, voice_message)
                return

            if not trips:
                return

            first_trip = trips[0]
            client_name = getattr(first_trip, "client_name", None) or getattr(first_trip, "get_client_name", lambda: None)()
            package_info = getattr(first_trip, "package_info", None) or getattr(first_trip, "get_package_info", lambda: None)()

            if client_name and package_info:
                summary_text = (
                    f"Hello {driver_name}, you have {len(trips)} trips. "
                    f"The first one is a {package_info} for {client_name}. "
                    "Have a great day."
                )
            elif client_name:
                summary_text = (
                    f"Hello {driver_name}, you have {len(trips)} trips. "
                    f"The first one is for {client_name}. "
                    "Have a great day."
                )
            else:
                summary_text = f"Hello {driver_name}, you have {len(trips)} trips. Have a great day."

            if self._ws_service is not None:
                await self._ws_service.send(session, {"type": "emotion", "name": "greeting"})
            await self.agent.speak_text(session, summary_text)
        except Exception:
            logger.exception("Error sending pending voice summary client_id=%s", session.client_id)
        finally:
            session._pending_voice_summary = None
