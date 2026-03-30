"""
services/agent_service.py
Orchestration centrale du pipeline IA : STT → LLM → TTS.

Responsabilité :
  - Recevoir un utterance complet (WAV bytes) depuis WebRTCService
  - Orchestrer STT → LLM (streaming) → TTS (streaming)
  - Alimenter le TTSAudioTrack de la session en temps réel
  - Gérer l'annulation si une nouvelle utterance arrive pendant le traitement
  - Mettre à jour l'historique de conversation dans la Session

Flux principal :
  wav_bytes → WhisperService.transcribe()
            → OllamaService.generate_stream()
            → PiperTTSService.synthesize_stream()
            → Session.tts_track.feed(samples)

Le lock session.processing_lock garantit qu'un seul pipeline
s'exécute par session à la fois.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from models.session import Session
    from services.whisper_service import WhisperService
    from services.ollama_service import OllamaService
    from services.piper_tts_service import PiperTTSService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService
    from services.intent_service import IntentService
    from services.denoise_service import DenoiseService

import config


class AgentService:
    """
    Singleton. Injecté dans WebRTCService.
    """

    def __init__(
        self,
        stt: "WhisperService",
        llm: "OllamaService",
        tts: "PiperTTSService",
        audio: "AudioService",
        intent: "IntentService | None" = None,
        denoise: "DenoiseService | None" = None,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio = audio
        self.intent = intent
        self.denoise = denoise
        # Référence optionnelle au WebSocketService pour envoyer
        # des événements texte au client (transcript, réponse LLM)
        self.ws_service: "WebSocketService | None" = None

    # ── Pipeline principal ────────────────────────────────────────────────────

    async def process_utterance(self, session: "Session", wav_bytes: bytes) -> None:
        """
        Point d'entrée principal. Appelé par WebRTCService après
        détection de fin d'utterance par le VAD.

        Étapes :
          1. Acquérir session.processing_lock (annuler si déjà en cours)
          2. Incrémenter session.current_request_id
          3. STT : WhisperService.transcribe(wav_bytes)
          4. Si transcript vide → relâcher le lock et retourner
          5. Notifier le client du transcript via WebSocketService (optionnel)
          6. Ajouter {"role":"user","content":transcript} à session.conversation_history
          7. LLM streaming → TTS streaming (voir _stream_response)
          8. Ajouter {"role":"assistant","content":full_reply} à l'historique
          9. session.trim_history(MAX_HISTORY, TRIM_TO)

        Gestion de l'annulation :
          Si session.cancel_flag est True à n'importe quelle étape → stopper.
          cancel_flag est mis à True par interrupt() avant de relancer process_utterance.
        """
        logger = logging.getLogger(__name__)

        # Si un pipeline est déjà en cours, on le coupe proprement.
        if session.processing_lock.locked():
            if not session.cancel_flag:
                await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False
            session.processing_started_at = time.monotonic()

            # STT
            try:
                stt_result = await self.stt.transcribe(wav_bytes)
            except Exception:
                logger.exception("STT error client_id=%s", session.client_id)
                return

            await self._process_transcription(session, request_id, stt_result.text)

    async def process_utterance_pcm(self, session: "Session", samples: "np.ndarray", sample_rate: int) -> None:
        """
        Entrée PCM/NumPy (recommandée pour WebRTC).
        """
        logger = logging.getLogger(__name__)
        if session.processing_lock.locked():
            if not session.cancel_flag:
                await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False
            session.processing_started_at = time.monotonic()

            import numpy as np

            if not isinstance(samples, np.ndarray):
                samples = np.asarray(samples, dtype=np.float32)
            samples = samples.astype(np.float32, copy=False).reshape(-1)

            # Debug audio stats
            if sample_rate > 0 and samples.size:
                dur_ms = float(samples.size / float(sample_rate) * 1000.0)
                rms = float(np.sqrt(np.mean(samples * samples)))
                peak = float(np.max(np.abs(samples)))
                logger.info(
                    "STT raw input client_id=%s ms=%.0f rms=%.4f peak=%.4f n=%d sr=%d",
                    session.client_id,
                    dur_ms,
                    rms,
                    peak,
                    int(samples.size),
                    int(sample_rate),
                )

            stt_samples = samples
            if _parse_bool(getattr(config, "DENOISE_FOR_STT", False)) and self.denoise is not None:
                try:
                    denoised = await self.denoise.process_utterance(samples, sample_rate=int(sample_rate))
                    if getattr(denoised, "size", 0):
                        stt_samples = denoised
                        if sample_rate > 0:
                            dur_ms = float(stt_samples.size / float(sample_rate) * 1000.0)
                            rms = float(np.sqrt(np.mean(stt_samples * stt_samples))) if stt_samples.size else 0.0
                            peak = float(np.max(np.abs(stt_samples))) if stt_samples.size else 0.0
                            logger.info(
                                "STT denoised input client_id=%s ms=%.0f rms=%.4f peak=%.4f n=%d sr=%d",
                                session.client_id,
                                dur_ms,
                                rms,
                                peak,
                                int(stt_samples.size),
                                int(sample_rate),
                            )
                except Exception:
                    logger.exception("STT utterance denoise failed client_id=%s", session.client_id)

            # Normaliser (aide Whisper sur segments faibles)
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
        logger = logging.getLogger(__name__)
        if session.cancel_flag or session.current_request_id != request_id:
            return

        transcript = _normalize_spaces(text or "")
        logger.info("STT transcript client_id=%s text_len=%d", session.client_id, len(transcript))
        if not transcript:
            if self.ws_service is not None:
                await self.ws_service.send(session, {"type": "stt_empty"})
            session.reset_interruption_state()
            return

        if self.ws_service is not None:
            await self.ws_service.send_transcript(session, transcript)

        effective_transcript = transcript
        if session.interruption_pending:
            decision = self._decide_interruption_mode(session, transcript)
            logger.info(
                "Interruption decision client_id=%s mode=%s elapsed_ms=%.0f transcript=%r",
                session.client_id,
                decision,
                session.interruption_elapsed_ms,
                transcript,
            )
            if self.ws_service is not None:
                await self.ws_service.send(
                    session,
                    {
                        "type": "interruption_decision",
                        "decision": decision,
                        "elapsed_ms": round(session.interruption_elapsed_ms, 1),
                        "text": transcript,
                    },
                )
            if decision == "continuation":
                effective_transcript = self._merge_with_active_user_turn(session, request_id, transcript)
            else:
                self._discard_active_user_turn(session)
            session.reset_interruption_state()

        # Intent detection (optionnel)
        detected_intent = None
        if self.intent is not None:
            try:
                detected_intent = await asyncio.to_thread(self.intent.getint, effective_transcript)
            except Exception:
                logger.exception("Intent detection error client_id=%s", session.client_id)
                detected_intent = None

            if self.ws_service is not None:
                await self.ws_service.send(
                    session,
                    {"type": "intent", "intent": detected_intent or "INCONNU"},
                )

            if _parse_bool(config.INTENT_GATE_LLM) and detected_intent and detected_intent != "INCONNU":
                session.clear_active_user_turn()
                return

        if session.active_user_message_index is None:
            session.conversation_history.append({"role": "user", "content": effective_transcript})
            session.mark_active_user_turn(
                request_id=request_id,
                index=len(session.conversation_history) - 1,
                text=effective_transcript,
            )
        else:
            session.mark_active_user_turn(
                request_id=request_id,
                index=session.active_user_message_index,
                text=effective_transcript,
            )

        # LLM -> TTS streaming
        full_reply = await self._stream_response(
            session=session,
            user_text=effective_transcript,
            request_id=request_id,
        )

        if session.cancel_flag or session.current_request_id != request_id:
            return

        if full_reply:
            session.conversation_history.append({"role": "assistant", "content": full_reply})
            session.trim_history(config.MAX_HISTORY, config.TRIM_TO)
        session.clear_active_user_turn()

    async def interrupt(self, session: "Session", *, event_type: str = "interrupted") -> None:
        """
        Annuler le traitement en cours pour cette session.

        Actions :
          1. session.cancel_flag = True
          2. Vider la queue du TTSAudioTrack si il existe
          3. Notifier le client via WebSocket {"type": "interrupted"}

        Appelé par WebRTCService quand une nouvelle utterance est détectée
        pendant qu'une réponse TTS est en cours de diffusion.
        """
        logger = logging.getLogger(__name__)
        logger.warning(
            "INTERRUPT called! client_id=%s tts_playing=%s processing_lock=%s cancel_flag=%s",
            session.client_id,
            session.tts_playing,
            session.processing_lock.locked(),
            session.cancel_flag,
        )

        session.cancel_flag = True
        if session.tts_track is not None:
            try:
                await session.tts_track.clear()
            except Exception:
                pass
        if self.ws_service is not None:
            await self.ws_service.send(session, {"type": event_type})
        session.reset_tts_output_state()
        session.tts_started_at = 0.0

    async def on_user_speech_start(self, session: "Session") -> None:
        if session.interruption_pending:
            return
        if not (session.tts_playing or session.processing_lock.locked()):
            return

        now = time.monotonic()
        reference = 0.0
        if session.tts_started_at > 0:
            reference = session.tts_started_at
        elif session.processing_started_at > 0:
            reference = session.processing_started_at
        elapsed_ms = max(0.0, (now - reference) * 1000.0) if reference > 0 else 0.0
        session.interruption_pending = True
        session.interruption_elapsed_ms = elapsed_ms
        await self.interrupt(session, event_type="tts_stop_now")

    async def speak_text(self, session: "Session", text: str) -> None:
        """
        Jouer un texte arbitraire via le pipeline TTS, sans passer par STT/LLM.
        Utilisé pour le bouton de test TTS dans la page.
        """
        logger = logging.getLogger(__name__)
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
            session.reset_tts_output_state()
            session.processing_started_at = time.monotonic()

            async def _text_stream():
                yield text

            session.tts_playing = True
            try:
                await self._play_tts_stream(
                    session=session,
                    request_id=request_id,
                    stream=self.tts.synthesize_stream(
                        _text_stream(),
                        cancel_check=lambda: session.cancel_flag or session.current_request_id != request_id,
                    ),
                    client_event_type="tts_test",
                    full_text_parts=None,
                )
            except Exception:
                logger.exception("TTS test playback error client_id=%s", session.client_id)
            finally:
                session.tts_playing = False
                session.reset_tts_output_state()
                session.tts_started_at = 0.0

    # ── Pipeline interne ─────────────────────────────────────────────────────

    async def _stream_response(
        self,
        session: "Session",
        user_text: str,
        request_id: int,
    ) -> str:
        """
        LLM streaming → TTS **non-streaming** (tout générer d'un coup) → TTSAudioTrack.

        Simplification : on attend que tout le TTS soit généré avant de jouer.
        """
        logger = logging.getLogger(__name__)
        if session.tts_track is None:
            return ""

        history = session.conversation_history
        
        # 1. Générer tout le texte du LLM
        full_reply = ""
        async for token in self.llm.generate_stream(user_text, history):
            if session.cancel_flag or session.current_request_id != request_id:
                return ""
            full_reply += token

        if not full_reply.strip():
            return ""

        # 2. Synthétiser TTS en un seul bloc
        session.tts_playing = True
        session.reset_tts_output_state()
        session.tts_started_at = time.monotonic()
        
        try:
            samples, rate = await self.tts.synthesize(full_reply)
            
            if session.cancel_flag or session.current_request_id != request_id:
                return full_reply
            
            # 3. Envoyer tous les frames d'un coup
            await self._emit_tts_audio(
                session=session,
                phrase_text=full_reply,
                samples=samples,
                rate=rate,
                client_event_type="response",
            )
            
            # Notifier le client
            if self.ws_service is not None:
                await self.ws_service.send_response_chunk(session, full_reply)
                
        except Exception:
            logger.exception("TTS synthesis error client_id=%s", session.client_id)
        finally:
            session.tts_playing = False
            session.reset_tts_output_state()
            session.tts_started_at = 0.0

        return full_reply

    async def _play_tts_stream(
        self,
        *,
        session: "Session",
        request_id: int,
        stream,
        client_event_type: str | None,
        full_text_parts: list[str] | None,
    ) -> None:
        logger = logging.getLogger(__name__)
        queue_maxsize = max(1, int(getattr(config, "TTS_SEGMENT_QUEUE_MAXSIZE", 3)))
        queue: asyncio.Queue = asyncio.Queue(maxsize=queue_maxsize)
        sentinel = object()

        async def _producer() -> None:
            try:
                async for phrase_text, samples, rate in stream:
                    if session.cancel_flag or session.current_request_id != request_id:
                        break
                    await queue.put((phrase_text, samples, rate))
            except Exception:
                logger.exception("TTS segment producer error client_id=%s", session.client_id)
            finally:
                await queue.put(sentinel)

        producer_task = asyncio.create_task(_producer())

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break

                phrase_text, samples, rate = item
                if session.cancel_flag or session.current_request_id != request_id:
                    break
                if full_text_parts is not None and phrase_text:
                    full_text_parts.append(phrase_text)
                await self._emit_tts_audio(
                    session=session,
                    phrase_text=phrase_text,
                    samples=samples,
                    rate=rate,
                    client_event_type=client_event_type,
                )
        finally:
            if not producer_task.done():
                producer_task.cancel()
            with suppress(asyncio.CancelledError):
                await producer_task

    async def _emit_tts_audio(
        self,
        session: "Session",
        phrase_text: str,
        samples,
        rate: int,
        *,
        client_event_type: str | None,
    ) -> None:
        logger = logging.getLogger(__name__)
        if phrase_text and self.ws_service is not None and client_event_type is not None:
            if client_event_type == "response":
                await self.ws_service.send_response_chunk(session, phrase_text)
            else:
                await self.ws_service.send(session, {"type": client_event_type, "text": phrase_text})

        samples = self._prepare_tts_samples(session, samples, int(rate))
        if samples is None or len(samples) == 0:
            return

        frames = self.audio.array_to_av_frames(
            samples,
            source_rate=rate,
            target_rate=config.AUDIO_OUTPUT_SAMPLE_RATE,  # 48kHz pour WebRTC
        )
        if samples is not None and len(samples) > 0:
            logger.info(
                "TTS audio client_id=%s phrase_len=%d src_rate=%d out_rate=%d samples=%d frames=%d",
                session.client_id,
                len(phrase_text or ""),
                int(rate),
                int(config.AUDIO_OUTPUT_SAMPLE_RATE),
                int(len(samples)),
                len(frames),
            )
        
        # Envoyer les frames au rythme réel (1 frame toutes les 20ms)
        for frame in frames:
            await session.tts_track.feed(frame)
            await asyncio.sleep(0.02)  # 20ms entre chaque frame

    def _prepare_tts_samples(self, session: "Session", samples, rate: int):
        """
        Prépare les samples TTS : trim_silence optionnel.
        Pas d'overlap : envoi direct.
        """
        logger = logging.getLogger(__name__)
        import numpy as np

        if samples is None:
            return np.array([], dtype=np.float32)
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples

        # Trim silence optionnel
        try:
            samples = self.audio.trim_silence(
                samples,
                sample_rate=int(rate),
                threshold=float(getattr(config, "TTS_TRIM_SILENCE_THRESHOLD", 0.003)),
                pad_ms=int(getattr(config, "TTS_TRIM_SILENCE_PAD_MS", 18)),
                min_silence_ms=int(getattr(config, "TTS_TRIM_MIN_SILENCE_MS", 80)),
                trim_leading=bool(getattr(config, "TTS_TRIM_LEADING", False)),
                trim_trailing=bool(getattr(config, "TTS_TRIM_TRAILING", True)),
            )
        except Exception:
            logger.debug("TTS trim_silence skipped", exc_info=True)

        if samples.size == 0:
            session.reset_tts_output_state()

        return samples

    async def _wait_for_tts_buffer_window(self, session: "Session", request_id: int) -> None:
        if session.cancel_flag or session.current_request_id != request_id:
            return
        track = session.tts_track
        if track is None:
            return
        waiter = getattr(track, "wait_until_buffer_below", None)
        if not callable(waiter):
            return
        low_watermark_ms = max(0, int(getattr(config, "TTS_BUFFER_LOW_WATERMARK_MS", 0)))
        if low_watermark_ms <= 0:
            return
        await waiter(low_watermark_ms)

    def _decide_interruption_mode(self, session: "Session", transcript: str) -> str:
        text = _normalize_spaces(transcript).lower()
        has_interrupt = _contains_trigger(text, tuple(getattr(config, "INTERRUPTION_WORDS_EN", ())))
        has_continuation = _contains_trigger(text, tuple(getattr(config, "CONTINUATION_WORDS_EN", ())))
        short_threshold_ms = float(getattr(config, "INTERRUPTION_SHORT_THRESHOLD_MS", 1000.0))
        if session.interruption_elapsed_ms < short_threshold_ms:
            if has_interrupt:
                return "interruption"
            if has_continuation:
                return "continuation"
            return "continuation"

        if has_continuation:
            return "continuation"
        if has_interrupt:
            return "interruption"
        return "interruption"

    def _merge_with_active_user_turn(self, session: "Session", request_id: int, transcript: str) -> str:
        merged = _normalize_spaces(f"{session.active_user_text} {transcript}")
        index = session.active_user_message_index
        if index is None or index < 0 or index >= len(session.conversation_history):
            session.conversation_history.append({"role": "user", "content": merged})
            index = len(session.conversation_history) - 1
        else:
            session.conversation_history[index]["content"] = merged
        session.mark_active_user_turn(request_id=request_id, index=index, text=merged)
        return merged

    def _discard_active_user_turn(self, session: "Session") -> None:
        index = session.active_user_message_index
        if index is not None and 0 <= index < len(session.conversation_history):
            message = session.conversation_history[index]
            if isinstance(message, dict) and message.get("role") == "user":
                del session.conversation_history[index]
        session.clear_active_user_turn()

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive pour éviter la dépendance circulaire."""
        self.ws_service = ws_service


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    v = str(value or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _normalize_spaces(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _contains_trigger(text: str, triggers: tuple[str, ...]) -> bool:
    haystack = f" {text.strip().lower()} "
    for trigger in triggers:
        normalized = _normalize_spaces(trigger).lower()
        if not normalized:
            continue
        if f" {normalized} " in haystack:
            return True
    return False
