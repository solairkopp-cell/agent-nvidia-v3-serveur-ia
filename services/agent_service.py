"""
services/agent_service.py
Orchestration centrale du pipeline IA : STT → LLM → TTS.

Logique TTS simplifiée :
  - LLM génère du texte → synthèse Piper → feed direct au tts_track
  - Si un TTS tourne déjà → fade-out 150ms + annulation → jouer le nouveau
  - Pas de queue de frames, pas de scheduler, pas de priorités

Flux principal :
  wav_bytes → WhisperService.transcribe()
            → OllamaService.stream_chat() (ou .chat())
            → PiperTTSService.synthesize(phrase)
            → tts_track.feed(samples)
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING
import uuid
from services.utility_service import UtilityService

import numpy as np

if TYPE_CHECKING:
    from models.session import Session
    from services.whisper_service import WhisperService
    from services.ollama_service import OllamaService
    from services.piper_client_service import PiperClientService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService
    from services.denoise_service import DenoiseService
    from services.delivery_state_machine import DeliveryStateMachine

import config
from services.driver_auth_utils import extract_driver_serial_from_transcript


logger = logging.getLogger(__name__)

class AgentService:
    """
    Singleton. Injecté dans le service de flux audio.
    """

    def __init__(
        self,
        stt: "WhisperService",
        llm: "OllamaService",
        tts: "PiperClientService",
        audio: "AudioService",
        denoise: "DenoiseService | None" = None,
        state_machine: "DeliveryStateMachine | None" = None,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio = audio
        self.denoise = denoise
        self.state_machine = state_machine
        self.ws_service: "WebSocketService | None" = None
        self.utility_service = UtilityService()

        self.tts.set_audio_callback(self._on_tts_audio_chunk)
        self._watchdog_task = asyncio.create_task(self._tts_watchdog())

    async def _on_tts_audio_chunk(self, samples: np.ndarray) -> None:
        if self.ws_service is None:
            return

        for session in list(self.ws_service._sessions.values()):
            if getattr(session, "tts_playing", False) and getattr(session, "tts_track", None) is not None:
                chunk_count = int(getattr(session, "_tts_debug_chunks", 0)) + 1
                session._tts_debug_chunks = chunk_count
                if chunk_count == 1 or chunk_count % 50 == 0:
                    logger.info(
                        "TTS audio chunk client_id=%s chunks=%d samples=%d",
                        session.client_id,
                        chunk_count,
                        int(samples.size),
                    )
                session.last_tts_audio_time = time.monotonic()
                await session.tts_track.feed(samples)

    async def _tts_watchdog(self) -> None:
        """Surveille l'inactivité de Piper pour repasser les sessions en 'idle'."""
        while True:
            await asyncio.sleep(0.1)
            if not self.ws_service:
                continue
            now = time.monotonic()
            for session in list(self.ws_service._sessions.values()):
                if getattr(session, "tts_playing", False) and getattr(session, "tts_feeding_done", False):
                    last_audio = getattr(session, "last_tts_audio_time", 0)
                    if now - last_audio > 4.0:
                        session.tts_playing = False
                        asyncio.create_task(self._send_emotion(session, "idle"))

    # ── Pipeline principal ────────────────────────────────────────────────────

    async def process_utterance(self, session: "Session", wav_bytes: bytes) -> None:

        if session.processing_lock.locked():
            await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False
            session.processing_started_at = time.monotonic()

            try:
                stt_result = await self.stt.transcribe(wav_bytes)
            except Exception:
                logger.exception("STT error client_id=%s", session.client_id)
                return

            await self._process_transcription(session, request_id, stt_result.text)

    async def process_utterance_pcm(
        self,
        session: "Session",
        samples: "np.ndarray",
        sample_rate: int,
        *,
        apply_denoise: bool = True,
        utterance_id: str | None = None,
    ) -> None:
        """Entrée PCM/NumPy."""
        if session.processing_lock.locked():
            await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False
            session.processing_started_at = time.monotonic()

            import numpy as np

            if not isinstance(samples, np.ndarray):
                samples = np.asarray(samples, dtype=np.float32)
            samples = samples.astype(np.float32, copy=False).reshape(-1)

            if sample_rate > 0 and samples.size:
                dur_ms = float(samples.size / float(sample_rate) * 1000.0)
                rms = float(np.sqrt(np.mean(samples * samples)))
                peak = float(np.max(np.abs(samples)))
                logger.info(
                    "STT raw input client_id=%s ms=%.0f rms=%.4f peak=%.4f n=%d sr=%d",
                    session.client_id, dur_ms, rms, peak, int(samples.size), int(sample_rate),
                )

            raw_stt_samples = samples.copy()
            stt_samples = samples

            if apply_denoise and getattr(config, "DENOISE_FOR_STT", False) and self.denoise is not None:
                try:
                    denoised = await self.denoise.process_utterance(samples, sample_rate=int(sample_rate))
                    if getattr(denoised, "size", 0):
                        stt_samples = denoised
                except Exception:
                    logger.exception("STT utterance denoise failed client_id=%s", session.client_id)

            self._save_debug_stt_audio(
                session, raw_stt_samples, stt_samples, int(sample_rate), utterance_id=utterance_id,
            )

            try:
                stt_samples = self.audio.normalize(stt_samples)
            except Exception:
                pass

            try:
                stt_result = await self.stt.transcribe_pcm(stt_samples, int(sample_rate))
            except Exception:
                logger.exception("STT pcm error client_id=%s", session.client_id)
                return

            await self._process_transcription(session, request_id, stt_result.text)

    async def _process_transcription(self, session: "Session", request_id: int, text: str | None) -> None:
        if session.cancel_flag or session.current_request_id != request_id:
            return

        transcript = _normalize_spaces(text or "")
        logger.info("STT transcript client_id=%s text=%r", session.client_id, transcript)
        if not transcript:
            if self.ws_service is not None:
                await self.ws_service.send(session, {"type": "stt_empty"})
            return

        if self.ws_service is not None:
            await self.ws_service.send_transcript(session, transcript)

        if getattr(session, "awaiting_driver_serial", False):
            await self._handle_voice_driver_serial_transcript(session, request_id, transcript)
            return

        # ── State Machine Processing (MODE_1) ─────────────────────────────────
        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            if session.tts_playing:
                logger.info(
                    "State machine: ignoring input during TTS client_id=%s transcript=%r",
                    session.client_id, transcript,
                )
                session.clear_active_user_turn()
                return

            try:
                state_result = await self.state_machine.process_input(
                    session=session,
                    transcript=transcript,
                )

                if state_result.should_handle:
                    if state_result.tts_response:
                        # Bypass LLM : la state machine génère des textes hardcodés,
                        # on les envoie directement à Piper TTS sans passer par le LLM.
                        await self._play_tts_simple(session, request_id, state_result.tts_response)

                    if state_result.action == "update_trip":
                        await self._handle_update_trip_action(session, state_result.action_params)

                    if state_result.next_state is not None:
                        ctx = self.state_machine._get_context(session)
                        ctx.state = state_result.next_state
                        logger.info(
                            "State machine: transitioned to %s client_id=%s",
                            state_result.next_state.value, session.client_id,
                        )

                    if state_result.action == "exit_to_mode_0" or (
                        state_result.next_state is not None
                        and state_result.next_state.value == "state_5"
                    ):
                        ctx = self.state_machine._get_context(session)
                        ctx.reset()
                        logger.info(
                            "State machine: exited to MODE_0 client_id=%s",
                            session.client_id,
                        )
                        session.clear_active_user_turn()
                        await self._drain_pending_arrived(session)
                        return

                    session.clear_active_user_turn()
                    return

            except Exception:
                logger.exception("State machine error client_id=%s", session.client_id)

        # Pipeline normal → envoyer au LLM
        if session.active_user_message_index is None:
            session.conversation_history.append({"role": "user", "content": transcript})
            session.mark_active_user_turn(
                request_id=request_id,
                index=len(session.conversation_history) - 1,
                text=transcript,
            )
        else:
            session.mark_active_user_turn(
                request_id=request_id,
                index=session.active_user_message_index,
                text=transcript,
            )

        full_reply = await self._stream_response(
            session=session,
            user_text=transcript,
            request_id=request_id,
        )

        if session.cancel_flag or session.current_request_id != request_id:
            return

        if full_reply:
            session.conversation_history.append({"role": "assistant", "content": full_reply})
            session.trim_history(config.MAX_HISTORY, config.TRIM_TO)
        session.clear_active_user_turn()

    # ── TTS simple ────────────────────────────────────────────────────────────

    async def _stop_current_tts_with_fade(
        self,
        session: "Session",
        *,
        notify_client_stop: bool = True,
    ) -> None:
        logger.info("TTS fade-out + stop client_id=%s", session.client_id)
        session.cancel_flag = True

        if session.tts_task is not None and not session.tts_task.done():
            session.tts_task.cancel()
            with suppress(asyncio.CancelledError):
                await session.tts_task

        if notify_client_stop and self.ws_service is not None:
            await self.ws_service.send(session, {"type": "tts_stop_now"})

        await self.tts.interrupt()

        fade_ms = int(getattr(config, "TTS_FADE_OUT_MS", 150))
        await asyncio.sleep(fade_ms / 1000.0)
        session.tts_playing = False
        session.cancel_flag = False

    async def _play_tts_simple(
        self,
        session: "Session",
        request_id: int,
        text: str,
        event_type: str = "response",
    ) -> None:
        
        text = (text or "").strip()
        if not text or session.tts_track is None:
            return

        if session.tts_playing:
            await self._stop_current_tts_with_fade(session)

        if session.cancel_flag or session.current_request_id != request_id:
            return

        await self._send_emotion(session, "speaking")

        if self.ws_service is not None:
            if event_type == "response":
                await self.ws_service.send_response_chunk(session, text)
            else:
                await self.ws_service.send(session, {"type": event_type, "text": text})

        session.tts_playing = True
        session.tts_feeding_done = False
        session.last_tts_audio_time = time.monotonic()
        session.tts_started_at = time.monotonic()
        session._tts_debug_chunks = 0
        session._tts_debug_started_at = time.monotonic()
        logger.info(
            "TTS start client_id=%s request_id=%s event_type=%s text_len=%d",
            session.client_id, request_id, event_type, len(text),
        )

        async def _do_play():
            try:
                if session.cancel_flag or session.current_request_id != request_id:
                    return
                await self.tts.feed_text(text)
                session.last_tts_audio_time = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TTS playback error client_id=%s", session.client_id)
            finally:
                if session.current_request_id == request_id:
                    session.tts_feeding_done = True

        tts_task = asyncio.create_task(_do_play(), name=f"tts-{session.client_id}")
        session.tts_task = tts_task
        try:
            await tts_task
        except asyncio.CancelledError:
            pass
        finally:
            started_at = float(getattr(session, "_tts_debug_started_at", time.monotonic()))
            elapsed_ms = (time.monotonic() - started_at) * 1000.0
            logger.info(
                "TTS end client_id=%s request_id=%s chunks=%d elapsed_ms=%.1f feeding_done=%s cancel_flag=%s",
                session.client_id, request_id,
                int(getattr(session, "_tts_debug_chunks", 0)),
                elapsed_ms,
                bool(getattr(session, "tts_feeding_done", False)),
                bool(getattr(session, "cancel_flag", False)),
            )

    # ── Pipeline LLM → TTS (stream) ───────────────────────────────────────────

    async def _stream_llm_to_tts(
        self,
        session: "Session",
        request_id: int,
        instruction: str,
    ) -> str:
        """
        Chemin générique stream : generate_system_reply → tts.stream_text → flush.
        Retourne le texte complet généré.
        """
        session.tts_playing = True
        session.tts_feeding_done = False
        session.last_tts_audio_time = time.monotonic()
        await self._send_emotion(session, "speaking")

        llm_chunks: list[str] = []

        async def _do_stream():
            try:
                async for chunk in self.llm.generate_system_reply(instruction, session=session):
                    if session.cancel_flag or session.current_request_id != request_id:
                        break
                    if chunk:
                        llm_chunks.append(chunk)
                        await self.tts.stream_text(chunk)
                        session.last_tts_audio_time = time.monotonic()
                if not session.cancel_flag and session.current_request_id == request_id:
                    await self.tts.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("TTS stream error client_id=%s", session.client_id)
            finally:
                session.tts_feeding_done = True

        tts_task = asyncio.create_task(_do_stream(), name=f"tts-{session.client_id}")
        session.tts_task = tts_task
        try:
            await tts_task
        except asyncio.CancelledError:
            pass

        return "".join(llm_chunks).strip()

    async def _rewrite_and_stream(
        self,
        session: "Session",
        *,
        text: str,
        context_hint: str = "general",
        request_id: int,
    ) -> str:
        """Réécrit `text` en anglais naturel et le streame directement vers Piper."""
        text = (text or "").strip()
        if not text:
            return text
        instruction = (
            "Answer the delivery driver using natural, concise spoken English. "
            "Keep the exact intent and factual meaning. Do not add new facts. "
            f"Context={context_hint}. Message: {text}"
        )
        reply = await self._stream_llm_to_tts(session, request_id, instruction)
        return reply or text

    async def _stream_response(
        self,
        session: "Session",
        user_text: str,
        request_id: int,
    ) -> str:
        """LLM → TTS → socket audio (pipeline normal MODE_0)."""
        import inspect
        

        if session.tts_track is None:
            return ""

        stream_chat = getattr(self.llm, "stream_chat", None)
        if config.OLLAMA_STREAM and inspect.isasyncgenfunction(stream_chat):
            llm_chunks: list[str] = []
            first_chunk_at: float | None = None

            async def _llm_gen():
                nonlocal first_chunk_at
                async for chunk in stream_chat(
                    user_text,
                    history=session.conversation_history,
                    session=session,
                ):
                    if session.cancel_flag or session.current_request_id != request_id:
                        break
                    if not chunk:
                        continue
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic()
                        logger.info(
                            "LLM first chunk client_id=%s latency_ms=%.1f",
                            session.client_id,
                            (first_chunk_at - session.processing_started_at) * 1000.0,
                        )
                    llm_chunks.append(chunk)
                    if self.ws_service is not None:
                        await self.ws_service.send_response_chunk(session, chunk)
                    yield chunk

            session.tts_playing = True
            session.tts_feeding_done = False
            session.last_tts_audio_time = time.monotonic()
            session.tts_started_at = time.monotonic()
            await self._send_emotion(session, "speaking")

            async def _do_play():
                try:
                    if session.cancel_flag or session.current_request_id != request_id:
                        return
                    async for chunk in _llm_gen():
                        if session.cancel_flag or session.current_request_id != request_id:
                            break
                        await self.tts.stream_text(chunk)
                        session.last_tts_audio_time = time.monotonic()
                    if not session.cancel_flag and session.current_request_id == request_id:
                        await self.tts.flush()
                        session.last_tts_audio_time = time.monotonic()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("TTS streaming playback error client_id=%s", session.client_id)
                finally:
                    if session.current_request_id == request_id:
                        session.tts_feeding_done = True

            tts_task = asyncio.create_task(_do_play(), name=f"tts-{session.client_id}")
            session.tts_task = tts_task
            try:
                await tts_task
            except asyncio.CancelledError:
                pass

            return "".join(llm_chunks).strip()

        # Mode non-streaming
        try:
            full_reply = await self.llm.chat(
                user_text,
                history=session.conversation_history,
                session=session,
            )
        except Exception:
            logger.exception("LLM chat error client_id=%s", session.client_id)
            return ""

        if session.cancel_flag or session.current_request_id != request_id:
            return ""
        if not full_reply.strip():
            return ""

        await self._play_tts_simple(session, request_id, full_reply)
        return full_reply

    # ── Interruption ──────────────────────────────────────────────────────────

    async def interrupt(self, session: "Session", *, event_type: str = "interrupted") -> None:
        
        logger.warning(
            "INTERRUPT called! client_id=%s tts_playing=%s",
            session.client_id, session.tts_playing,
        )

        session.cancel_flag = True

        if session.tts_task is not None and not session.tts_task.done():
            session.tts_task.cancel()
            with suppress(asyncio.CancelledError):
                await session.tts_task

        session.tts_playing = False
        if self.ws_service is not None:
            await self.ws_service.send(session, {"type": event_type})

    async def on_user_speech_start(self, session: "Session") -> None:
        
        if not (session.tts_playing or session.processing_lock.locked()):
            return

        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            logger.info("🔇 Interruption blocked (MODE_1 active) client_id=%s", session.client_id)
            return

        logger.info("User speech detected during TTS → interrupting client_id=%s", session.client_id)
        await self.interrupt(session, event_type="tts_stop_now")

    # ── speak_text ────────────────────────────────────────────────────────────

    async def speak_text(
        self,
        session: "Session",
        text: str,
        *,
        event_type: str = "response",
    ) -> None:
        
        text = (text or "").strip()
        if not text:
            return
        if session.tts_track is None:
            logger.warning("TTS test requested without active tts_track client_id=%s", session.client_id)
            return

        if session.processing_lock.locked():
            await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False
            await self._play_tts_simple(session, request_id, text, event_type=event_type)

    # ── Utilitaires ──────────────────────────────────────────────────────────
    async def start_voice_driver_auth(self, session: "Session") -> None:
        """Démarrer l'identification vocale du driver avec une phrase fixe."""
        session.auth_mode = "voice_driver_serial"
        session.awaiting_driver_serial = True
        session.auth_attempts = 0

        if self.ws_service is not None:
            await self.ws_service.send(
                session,
                {
                    "type": "auth",
                    "event": "awaiting_driver_serial",
                    "mode": "voice_driver_serial",
                },
            )

        await self.speak_text(
            session,
            "Welcome driver, identify yourself. Please say your driver number.",
            event_type="auth_prompt",
        )

    async def _handle_voice_driver_serial_transcript(
        self,
        session: "Session",
        request_id: int,
        transcript: str,
    ) -> None:
        driver_serial = extract_driver_serial_from_transcript(transcript)

        if not driver_serial:
            session.auth_attempts += 1
            if self.ws_service is not None:
                await self.ws_service.send(
                    session,
                    {
                        "type": "auth",
                        "event": "driver_serial_not_understood",
                        "attempts": session.auth_attempts,
                    },
                )
            await self._play_tts_simple(
                session,
                request_id,
                "I did not catch your driver number. Please repeat it.",
                event_type="auth_prompt",
            )
            return

        if self.ws_service is not None:
            await self.ws_service.send(
                session,
                {
                    "type": "auth",
                    "event": "driver_serial_detected",
                    "driver_serial": driver_serial,
                    "transcript": transcript,
                },
            )

            notification = getattr(self.ws_service, "notification", None)
            if notification is not None:
                await notification.on_message(
                    session,
                    {
                        "type": "identify_driver",
                        "driver_serial": driver_serial,
                        "source": "voice",
                    },
                )
                return

            await self.ws_service.send(
                session,
                {
                    "type": "auth",
                    "event": "error",
                    "message": "notification service unavailable",
                },
            )

    async def speak_instruction(
        self,
        session: "Session",
        *,
        instruction: str,
        fallback: str,
        event_type: str = "response",
    ) -> None:
        if session.tts_track is None:
            return
        request_id = session.next_request_id()
        session.cancel_flag = False
        reply = await self._stream_llm_to_tts(session, request_id, instruction)
        if not reply:
            await self._play_tts_simple(session, request_id, fallback, event_type=event_type)
            
    async def handle_external_control(
        self,
        session: "Session",
        action: str,
        extras: dict,
    ) -> None:
        
        logger.info(
            "📮 EXTERNAL CONTROL REÇU client_id=%s action=%s extras=%r",
            session.client_id, action, extras,
        )

        if action == "arrived":
            logger.info("✅ Traitement action arrived pour client_id=%s", session.client_id)
            await self._handle_arrived_action(session, extras)
        elif action == "started_navigation":
            logger.info("✅ Traitement action started_navigation pour client_id=%s", session.client_id)
            await self._handle_started_navigation_action(session, extras)
        elif action == "completed_delivery":
            logger.info("✅ Traitement action completed_delivery pour client_id=%s", session.client_id)
            await self._handle_completed_delivery_action(session, extras)
        elif action == "photo_taken":
            logger.info("✅ Traitement action photo_taken pour client_id=%s", session.client_id)
            await self._handle_photo_taken_action(session, photo_taken=True)
        elif action == "photo_not_taken":
            logger.info("✅ Traitement action photo_not_taken pour client_id=%s", session.client_id)
            await self._handle_photo_taken_action(session, photo_taken=False)
        else:
            logger.warning("❌ Action external_control inconnue: %s", action)

    async def _handle_photo_taken_action(self, session: "Session", photo_taken: bool) -> None:
        
        if self.state_machine is None:
            logger.warning("⚠️ State machine non disponible client_id=%s", session.client_id)
            return
        await self.state_machine.handle_photo_response(session, photo_taken)
        await self._drain_pending_arrived(session)

    async def _handle_arrived_action(self, session: "Session", extras: dict) -> None:
        
        trip_id = extras.get("trip_id")

        if not trip_id:
            logger.warning("⚠️ arrived action: missing trip_id client_id=%s", session.client_id)
            return

        logger.info("_handle_arrived_action: DRIVER ARRIVÉ client_id=%s trip_id=%s", session.client_id, trip_id)

        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            active_trip_id = getattr(session, "current_trip_id", None)
            if active_trip_id and active_trip_id != trip_id:
                session.pending_arrived_trip_id = trip_id
                logger.info(
                    "⏸️ arrived deferred while MODE_1 active client_id=%s pending_trip_id=%s",
                    session.client_id, trip_id,
                )
                return

        if session.tts_playing:
            await self._stop_current_tts_with_fade(session, notify_client_stop=False)

        session.tts_playing = False
        session.cancel_flag = False
        session.current_trip_id = trip_id

        if self.state_machine is not None:
            logger.info("🚀 Démarrage de la state machine pour client_id=%s", session.client_id)
            await self.state_machine.enter_mode_1(session)
            self.utility_service.current_trip_id = trip_id
            text = f"Is the  {self.utility_service.get_delivery_info(trip_id)} completed?"
            session.conversation_history.append({"role": "assistant", "content": text})
            logger.info("🗣️ TTS question de livraison client_id=%s", session.client_id)

            request_id = session.next_request_id()
            session.cancel_flag = False
            await self._play_tts_simple(session, request_id, text)
        else:
            logger.warning("⚠️ State machine non disponible client_id=%s", session.client_id)

    async def _consume_pending_arrived(self, session: "Session") -> None:
        pending_trip_id = getattr(session, "pending_arrived_trip_id", None)
        if not pending_trip_id:
            return
        session.pending_arrived_trip_id = None
        logger.info(
            "▶️ consuming deferred arrived client_id=%s trip_id=%s",
            session.client_id, pending_trip_id,
        )
        await self._handle_arrived_action(session, {"trip_id": pending_trip_id})

    async def _drain_pending_arrived(self, session: "Session") -> None:
        if not getattr(session, "pending_arrived_trip_id", None):
            return

        if session.processing_lock.locked():
            asyncio.create_task(
                self._consume_pending_arrived_when_unlocked(session),
                name=f"pending-arrived-{session.client_id}",
            )
            return

        await self._consume_pending_arrived(session)

    async def _consume_pending_arrived_when_unlocked(self, session: "Session") -> None:
        while session.processing_lock.locked():
            await asyncio.sleep(0.01)
        await self._consume_pending_arrived(session)

    async def _handle_started_navigation_action(self, session: "Session", extras: dict) -> None:
        
        trip_id = extras.get("trip_id")
        logger.info(
            "🗺️ Navigation started client_id=%s trip_id=%s",
            session.client_id, trip_id or "N/A",
        )

    async def _handle_completed_delivery_action(self, session: "Session", extras: dict) -> None:
        
        trip_id = extras.get("trip_id")
        status = extras.get("status", "COMPLETED")
        cause = extras.get("cause")
        reason = extras.get("reason")

        if not trip_id:
            logger.warning("completed_delivery action: missing trip_id client_id=%s", session.client_id)
            return

        logger.info(
            "✅ Delivery completed client_id=%s trip_id=%s status=%s",
            session.client_id, trip_id, status,
        )

        if self.state_machine is not None:
            success = await self.state_machine.update_trip_status(
                driver_serial=session.driver_serial,
                trip_id=trip_id,
                status=status,
                cause=cause,
                reason=reason,
            )
            if success:
                logger.info("✅ Trip status updated client_id=%s trip_id=%s", session.client_id, trip_id)
                session.conversation_history.append({
                    "role": "user",
                    "content": f"[SYSTEM MESSAGE] The delivery process is finished. The delivery has been marked as {status}."
                })

    async def _handle_update_trip_action(self, session: "Session", params: dict) -> None:
        
        if self.state_machine is None:
            return

        driver_serial = getattr(session, "driver_serial", None)
        if not driver_serial:
            logger.warning("update_trip action: missing driver_serial client_id=%s", session.client_id)
            return

        trip_id = getattr(session, "current_trip_id", None)
        if not trip_id:
            logger.warning("update_trip action: missing trip_id client_id=%s", session.client_id)
            return

        status = params.get("status", "COMPLETED")
        cause = params.get("cause")
        reason = params.get("reason")

        success = await self.state_machine.update_trip_status(
            driver_serial=driver_serial,
            trip_id=trip_id,
            status=status,
            cause=cause,
            reason=reason,
        )
        if success:
            logger.info("✅ Trip updated client_id=%s trip_id=%s status=%s", session.client_id, trip_id, status)
            session.conversation_history.append({
                "role": "user",
                "content": f"[SYSTEM MESSAGE] The delivery process is finished. The delivery has been marked as {status}."
            })
        else:
            logger.error("❌ Trip update failed client_id=%s trip_id=%s", session.client_id, trip_id)

    def _save_debug_stt_audio(
        self,
        session: "Session",
        raw_samples: np.ndarray,
        denoised_samples: np.ndarray,
        sample_rate: int,
        *,
        utterance_id: str | None = None,
    ) -> None:
        
        try:
            recordings_dir = Path("assets/recordings")
            recordings_dir.mkdir(parents=True, exist_ok=True)

            utterance_id = str(utterance_id or uuid.uuid4().hex[:8])
            client_id = str(getattr(session, "client_id", "unknown")).replace("/", "_")
            prefix = f"audio_{client_id}_{utterance_id}"

            raw_path = recordings_dir / f"{prefix}_raw.wav"
            denoised_path = recordings_dir / f"{prefix}_denoised.wav"

            self.audio.save_wav(raw_path, np.asarray(raw_samples, dtype=np.float32), sample_rate=sample_rate)
            self.audio.save_wav(denoised_path, np.asarray(denoised_samples, dtype=np.float32), sample_rate=sample_rate)

            raw_rms = float(np.sqrt(np.mean(raw_samples * raw_samples))) if raw_samples.size else 0.0
            denoised_rms = float(np.sqrt(np.mean(denoised_samples * denoised_samples))) if denoised_samples.size else 0.0

            logger.info(
                "Saved STT audio compare client_id=%s raw=%s denoised=%s raw_rms=%.6f denoised_rms=%.6f sr=%d",
                session.client_id, raw_path.name, denoised_path.name, raw_rms, denoised_rms, sample_rate,
            )
        except Exception:
            logger.exception("Failed to save STT comparison audio client_id=%s", session.client_id)

    async def _send_emotion(self, session: "Session", name: str) -> None:
        if self.ws_service is None:
            return
        try:
            await self.ws_service.send(session, {"type": "emotion", "name": str(name)})
        except Exception:
            pass

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive pour éviter la dépendance circulaire."""
        self.ws_service = ws_service


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()
