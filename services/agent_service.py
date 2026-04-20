"""
services/agent_service.py
Orchestration centrale du pipeline IA : STT → LLM → TTS.

Responsabilité :
  - Recevoir un utterance complet (WAV bytes) depuis WebRTCService
  - Orchestrer STT → LLM → TTS
  - Alimenter le TTSAudioTrack de la session en temps réel
  - Gérer l'annulation si une nouvelle utterance arrive pendant le traitement
  - Mettre à jour l'historique de conversation dans la Session

Flux principal :
  wav_bytes → WhisperService.transcribe()
            → OllamaService.chat()
            → PiperTTSService.synthesize()
            → Queue audio → Scheduler (20ms) → TTSAudioTrack

Le lock session.processing_lock garantit qu'un seul pipeline
s'exécute par session à la fois.
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING
import uuid

import numpy as np

if TYPE_CHECKING:
    from models.session import Session
    from services.whisper_service import WhisperService
    from services.ollama_service import OllamaService
    from services.piper_tts_service import PiperTTSService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService
    from services.denoise_service import DenoiseService
    from services.delivery_state_machine import DeliveryStateMachine

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
        denoise: "DenoiseService | None" = None,
        state_machine: "DeliveryStateMachine | None" = None,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.audio = audio
        self.denoise = denoise
        self.state_machine = state_machine
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
          7. LLM → TTS (voir _stream_response)
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

    async def process_utterance_pcm(
        self,
        session: "Session",
        samples: "np.ndarray",
        sample_rate: int,
        *,
        apply_denoise: bool = True,
        utterance_id: str | None = None,
    ) -> None:
        """
        Entrée PCM/NumPy (recommandée pour WebRTC).

        Args:
            apply_denoise: Autorise le denoise avant STT.
                Le traitement ne sera réellement appliqué que si
                config.DENOISE_FOR_STT est activé.
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

            # Sauvegarde de référence du brut reçu côté WebRTC
            raw_stt_samples = samples.copy()

            # Appliquer le denoise sur l'audio avant STT
            stt_samples = samples
            if apply_denoise and getattr(config, "DENOISE_FOR_STT", False) and self.denoise is not None:
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

            self._save_debug_stt_audio(
                session,
                raw_stt_samples,
                stt_samples,
                int(sample_rate),
                utterance_id=utterance_id,
            )

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
        logger.info("STT transcript client_id=%s text=%r", session.client_id, transcript)
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

        # ── State Machine Processing (MODE_1) ─────────────────────────────────
        # Si la machine à états est active, elle prioritaire sur le pipeline normal
        # Mais on ignore les inputs pendant que le TTS parle (sauf interruption)
        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            # Si le TTS est en train de parler, on ignore l'input utilisateur
            # pour éviter de traiter des commandes parlées pendant la réponse
            if session.tts_playing:
                logger.info(
                    "State machine: ignoring input during TTS client_id=%s transcript=%r",
                    session.client_id,
                    effective_transcript,
                )
                session.clear_active_user_turn()
                return

            try:
                state_result = await self.state_machine.process_input(
                    session=session,
                    transcript=effective_transcript,
                )

                if state_result.should_handle:
                    # La machine à états gère cet input
                    if state_result.tts_response:
                        # Envoyer la réponse TTS
                        await self._speak_state_response(
                            session,
                            request_id,
                            state_result.tts_response,
                            interruptible=state_result.interruptible,
                            emit_boundary_emotions=state_result.emit_tts_boundary_emotions,
                        )

                    if state_result.action == "update_trip":
                        # Mettre à jour le trip via PlanningService
                        await self._handle_update_trip_action(
                            session,
                            state_result.action_params,
                        )

                    # Mettre à jour l'état de la session APRÈS le TTS
                    # On applique la transition d'état retournée par la state machine
                    if state_result.next_state is not None:
                        ctx = self.state_machine._get_context(session)
                        ctx.state = state_result.next_state
                        logger.info(
                            "State machine: transitioned to %s client_id=%s",
                            state_result.next_state.value,
                            session.client_id,
                        )

                        # Si le flow est terminé, on sort immédiatement de MODE_1
                        # sans attendre une nouvelle parole utilisateur. Cela évite
                        # qu'un "arrived" suivant ou qu'une réponse tardive soit
                        # interprété(e) par STATE_5 du cycle précédent.
                        if state_result.next_state.value == "state_5":
                            ctx.reset()
                            logger.info(
                                "State machine: auto-reset to MODE_0 after terminal transition client_id=%s",
                                session.client_id,
                            )
                            await self._consume_pending_arrived(session)

                    if state_result.action == "exit_to_mode_0":
                        # Retour au MODE_0 (sur input utilisateur en STATE_5)
                        ctx = self.state_machine._get_context(session)
                        ctx.reset()
                        session.clear_active_user_turn()
                        return

                    session.clear_active_user_turn()
                    return
                # else: should_handle=False → continuer avec le pipeline normal (MODE_0)

            except Exception:
                logger.exception("State machine error client_id=%s", session.client_id)
                # En cas d'erreur, on continue avec le pipeline normal

        # Pipeline normal → envoyer au LLM
        llm_user_text = effective_transcript
        if session.active_user_message_index is None:
            session.conversation_history.append({"role": "user", "content": llm_user_text})
            session.mark_active_user_turn(
                request_id=request_id,
                index=len(session.conversation_history) - 1,
                text=llm_user_text,
            )
        else:
            session.mark_active_user_turn(
                request_id=request_id,
                index=session.active_user_message_index,
                text=llm_user_text,
            )

        # LLM -> TTS
        full_reply = await self._stream_response(
            session=session,
            user_text=llm_user_text,
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
        logger = logging.getLogger(__name__)
        if session.interruption_pending:
            return
        if not (session.tts_playing or session.processing_lock.locked()):
            return

        # Si on est dans le flow de livraison, on ignore toute tentative
        # d'interruption pendant la question/annonce critique.
        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            logger.info(
                "🔇 Interruption blocked (MODE_1 active) client_id=%s state=%s",
                session.client_id,
                self.state_machine.get_session_state(session)[1].value,
            )
            return

        # Vérifier si le TTS en cours est interruptible
        if not session.tts_interruptible:
            logger.info(
                "🔇 Interruption blocked (non-interruptible TTS) client_id=%s",
                session.client_id,
            )
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

    async def speak_text(
        self,
        session: "Session",
        text: str,
        interruptible: bool = True,
        emit_boundary_emotions: bool = True,
    ) -> None:
        """
        Jouer un texte arbitraire via le pipeline TTS, sans passer par STT/LLM.
        Utilisé pour le bouton de test TTS dans la page.

        Args:
            session: Session WebSocket
            text: Texte à synthétiser
            interruptible: Si True, l'utilisateur peut interrompre ce TTS
            emit_boundary_emotions: Si True, envoie les émotions automatiques
                de début/fin de parole ("speaking" / "idle").
        """
        logger = logging.getLogger(__name__)
        text = (text or "").strip()
        if not text:
            return
        if session.tts_track is None:
            logger.warning("TTS test requested without active tts_track client_id=%s", session.client_id)
            return

        # Interruption si un pipeline est en cours
        if session.processing_lock.locked():
            await self.interrupt(session)

        async with session.processing_lock:
            await self._speak_text_internal(
                session,
                text,
                interruptible,
                emit_boundary_emotions=emit_boundary_emotions,
            )

    async def _speak_text_internal(
        self,
        session: "Session",
        text: str,
        interruptible: bool = True,
        emit_boundary_emotions: bool = True,
    ) -> None:
        """
        Implémentation interne de speak_text, sans acquisition du lock.
        À utiliser quand le lock est déjà acquis.

        Args:
            session: Session WebSocket
            text: Texte à synthétiser
            interruptible: Si True, l'utilisateur peut interrompre ce TTS
            emit_boundary_emotions: Si True, envoie les émotions automatiques
                de début/fin de parole ("speaking" / "idle").
        """
        logger = logging.getLogger(__name__)
        text = (text or "").strip()
        if not text:
            return
        if session.tts_track is None:
            logger.warning("TTS test requested without active tts_track client_id=%s", session.client_id)
            return

        request_id = session.next_request_id()
        session.cancel_flag = False
        session.reset_tts_output_state()
        session.processing_started_at = time.monotonic()
        session.tts_interruptible = interruptible  # Définir si interruptible

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
                emit_boundary_emotions=emit_boundary_emotions,
            )
        except Exception:
            logger.exception("TTS test playback error client_id=%s", session.client_id)
        finally:
            session.tts_playing = False
            session.reset_tts_output_state()
            session.tts_started_at = 0.0
            session.tts_interruptible = True  # Reset à True par défaut
            # Réinitialiser l'état VAD pour que la prochaine parole soit détectée
            session.reset_audio_buffer()
            if hasattr(session, "vad_h"):
                session.vad_h = None
            if hasattr(session, "vad_c"):
                session.vad_c = None
            if emit_boundary_emotions:
                await self._send_emotion(session, "idle")

    # ── Pipeline interne ─────────────────────────────────────────────────────

    async def _stream_response(
        self,
        session: "Session",
        user_text: str,
        request_id: int,
        interruptible: bool = True,
    ) -> str:
        """
        LLM non-streaming → TTS non-streaming → TTSAudioTrack via queue + scheduler.
        """
        if session.tts_track is None:
            return ""

        full_reply = await self.llm.chat(
            user_text,
            history=session.conversation_history,
            session=session,
        )
        if session.cancel_flag or session.current_request_id != request_id:
            return ""
        if not full_reply.strip():
            return ""

        session.tts_playing = True
        session.reset_tts_output_state()
        session.tts_started_at = time.monotonic()
        session.tts_interruptible = interruptible

        scheduler_task = asyncio.create_task(
            self._tts_scheduler(session, request_id),
            name=f"tts-scheduler-{session.client_id}"
        )

        try:
            samples, rate = await self.tts.synthesize(full_reply)

            if session.cancel_flag or session.current_request_id != request_id:
                return full_reply

            # Envoyer l'émotion "speaking" avant la réponse
            try:
                if self.ws_service is not None:
                    await self.ws_service.send(session, {"type": "emotion", "name": "speaking"})
            except Exception:
                pass  # Ignorer silencieusement pour ne pas bloquer le TTS

            await self._emit_tts_audio(
                session=session,
                phrase_text=full_reply,
                samples=samples,
                rate=rate,
                client_event_type="response",
            )

            # Attendre que la queue soit presque vide
            await self._wait_queue_empty(session, request_id, timeout=2.0)

            # Flush de fin : 100ms de silence
            await self._flush_tts_queue(session, request_id, silence_frames=5)

            # Attendre que le flush soit consommé
            await asyncio.sleep(0.15)

        except Exception:
            logger.exception("TTS synthesis error client_id=%s", session.client_id)
        finally:
            # Arrêter le scheduler
            if not scheduler_task.done():
                scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task

            session.tts_playing = False
            session.reset_tts_output_state()
            session.tts_started_at = 0.0
            session.tts_interruptible = True  # Reset à True par défaut
            # Réinitialiser l'état VAD pour que la prochaine parole soit détectée
            session.reset_audio_buffer()
            if hasattr(session, "vad_h"):
                session.vad_h = None
            if hasattr(session, "vad_c"):
                session.vad_c = None
            await self._send_emotion(session, "idle")

        return full_reply

    async def _play_tts_stream(
        self,
        *,
        session: "Session",
        request_id: int,
        stream,
        client_event_type: str | None,
        full_text_parts: list[str] | None,
        emit_boundary_emotions: bool = True,
    ) -> None:
        """
        Jouer le flux TTS avec scheduler temps réel et queue audio.

        Architecture :
          - Producer : synthétise les segments TTS → met dans session.tts_audio_queue
          - Scheduler : consomme la queue → envoie frames à intervalle fixe (20ms)
          - Flush : ajoute 100ms de silence à la fin
        """
        logger = logging.getLogger(__name__)

        if emit_boundary_emotions:
            # Envoyer l'émotion "speaking" au début de chaque prise de parole
            try:
                if self.ws_service is not None:
                    await self.ws_service.send(session, {"type": "emotion", "name": "speaking"})
            except Exception:
                pass  # Ignorer silencieusement pour ne pas bloquer le TTS

        # Démarrer le scheduler en tâche de fond
        scheduler_task = asyncio.create_task(
            self._tts_scheduler(session, request_id),
            name=f"tts-scheduler-{session.client_id}"
        )
        
        try:
            # Traiter chaque segment du flux TTS
            async for phrase_text, samples, rate in stream:
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
                
        except Exception:
            logger.exception("TTS stream playback error client_id=%s", session.client_id)
        finally:
            # Si annulé, sortir immédiatement sans attendre
            if session.cancel_flag or session.current_request_id != request_id:
                # Vider la queue
                while not session.tts_audio_queue.empty():
                    try:
                        session.tts_audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                # Annuler le scheduler
                if scheduler_task and not scheduler_task.done():
                    scheduler_task.cancel()
            else:
                # Attendre que la queue soit presque vide
                await self._wait_queue_empty(session, request_id, timeout=2.0)

                # Flush de fin : 100ms de silence (5 frames)
                await self._flush_tts_queue(session, request_id, silence_frames=5)

                # Attendre que le flush soit consommé
                await asyncio.sleep(0.15)

                # Arrêter le scheduler
                if scheduler_task and not scheduler_task.done():
                    scheduler_task.cancel()
            
            with suppress(asyncio.CancelledError):
                await scheduler_task

    async def _emit_tts_audio(
        self,
        session: "Session",
        phrase_text: str,
        samples,
        rate: int,
        *,
        client_event_type: str | None,
    ) -> None:
        """
        Émettre l'audio TTS via une queue avec scheduler temps réel stable.
        
        Pipeline :
          1. S'assurer que samples est float32
          2. Découpage en frames strictes de 960 samples (20ms @ 48k)
          3. Mettre dans tts_audio_queue (float32)
          4. Le scheduler convertit float32→int16 et envoie à intervalle fixe
        """
        logger = logging.getLogger(__name__)
        if phrase_text and self.ws_service is not None and client_event_type is not None:
            if client_event_type == "response":
                await self.ws_service.send_response_chunk(session, phrase_text)
            else:
                await self.ws_service.send(session, {"type": client_event_type, "text": phrase_text})

        # Préparation samples
        samples = self._prepare_tts_samples(session, samples, int(rate))
        if samples is None or len(samples) == 0:
            return

        # S'assurer qu'on a du float32
        if samples.dtype != np.float32:
            samples = samples.astype(np.float32)

        samples = samples.reshape(-1)

        if samples.size == 0:
            return

        logger.info(
            "TTS audio client_id=%s phrase_len=%d rate=%d samples=%d dtype=%s",
            session.client_id,
            len(phrase_text or ""),
            int(rate),
            int(len(samples)),
            samples.dtype,
        )

        # Découpage strict en frames de 960 samples
        FRAME_SIZE = 960
        idx = 0
        frames_count = 0
        
        while idx + FRAME_SIZE <= len(samples):
            frame = samples[idx:idx + FRAME_SIZE].copy()
            await session.tts_audio_queue.put(frame)
            idx += FRAME_SIZE
            frames_count += 1

        # Reste (si < 960 samples) → compléter avec silence
        remainder = len(samples) - idx
        if remainder > 0:
            frame = np.zeros(FRAME_SIZE, dtype=np.float32)
            frame[:remainder] = samples[idx:]
            await session.tts_audio_queue.put(frame)
            frames_count += 1

        logger.info(
            "TTS frames queued client_id=%s frames=%d",
            session.client_id,
            frames_count,
        )

    def _prepare_tts_samples(self, session: "Session", samples, rate: int):
        """
        Prépare les samples TTS : trim_silence optionnel.
        Pas de resampling : TTS sort déjà en 48kHz et WebRTC attend 48kHz.
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

        # Trim silence avec seuil très bas et padding généreux
        if getattr(config, "TTS_TRIM_TRAILING", False):
            try:
                samples = self.audio.trim_silence(
                    samples,
                    sample_rate=int(rate),
                    threshold=float(getattr(config, "TTS_TRIM_SILENCE_THRESHOLD", 0.0001)),
                    pad_ms=int(getattr(config, "TTS_TRIM_SILENCE_PAD_MS", 80)),
                    min_silence_ms=int(getattr(config, "TTS_TRIM_MIN_SILENCE_MS", 150)),
                    trim_leading=bool(getattr(config, "TTS_TRIM_LEADING", False)),
                    trim_trailing=True,
                )
            except Exception:
                logger.debug("TTS trim_silence skipped", exc_info=True)

        if samples.size == 0:
            session.reset_tts_output_state()

        return samples

    def _apply_crossfade(self, samples: np.ndarray, rate: int, overlap_ms: int = 30) -> np.ndarray:
        """
        Applique un fondu enchaîné (crossfade) entre les segments TTS pour éviter
        les coupures sèches qui créent des artefacts de type 'clic'.
        Force la waveform à zéro aux extrémités pour éviter les discontinuités de phase.
        """
        import numpy as np
        
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            return samples
        
        overlap_samples = int(rate * (overlap_ms / 1000.0))
        if overlap_samples <= 0 or overlap_samples >= len(samples) // 2:
            return samples
        
        # Force waveform à zéro aux extrémités + fade
        # Fade-in au début (part de 0)
        fade_in = np.linspace(0.0, 1.0, overlap_samples, dtype=np.float32) ** 2  # Courbe exponentielle
        samples[:overlap_samples] *= fade_in
        
        # Fade-out à la fin (revient à 0)
        fade_out = np.linspace(1.0, 0.0, overlap_samples, dtype=np.float32) ** 2  # Courbe exponentielle
        samples[-overlap_samples:] *= fade_out
        
        return samples

    async def _tts_scheduler(self, session: "Session", request_id: int) -> None:
        """
        Scheduler temps réel pour envoyer les frames audio à intervalle fixe.

        Utilise un accumulateur de temps pour éviter le drift.
        Fallback silence si la queue est vide.
        """
        logger = logging.getLogger(__name__)
        FRAME_DURATION = 0.02  # 20ms
        FRAME_SIZE = 960

        loop = asyncio.get_event_loop()
        next_time = loop.time()

        # Silence frame en float32 (coherent avec la queue)
        silence_frame = np.zeros(FRAME_SIZE, dtype=np.float32)

        try:
            while not session.cancel_flag and session.current_request_id == request_id:
                try:
                    # Attendre une frame avec timeout
                    frame = await asyncio.wait_for(
                        session.tts_audio_queue.get(),
                        timeout=FRAME_DURATION
                    )
                except asyncio.TimeoutError:
                    # Timeout → frame silence pour éviter les trous
                    frame = silence_frame

                # Envoyer la frame au track (array_to_av_frame convertit float32→int16)
                if session.tts_track is not None:
                    av_frame = self.audio.array_to_av_frame(frame, sample_rate=48000)
                    await session.tts_track.feed(av_frame)

                # Scheduler : attendre le bon moment
                next_time += FRAME_DURATION
                sleep_time = next_time - loop.time()

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception:
            logger.exception("TTS scheduler error client_id=%s", session.client_id)
        finally:
            logger.info("TTS scheduler stopped client_id=%s", session.client_id)

    async def _flush_tts_queue(self, session: "Session", request_id: int, silence_frames: int = 5) -> None:
        """
        Ajouter un flush de silence à la fin du TTS (100ms = 5 frames).
        Permet d'éviter la coupure brutale du dernier son.
        """
        FRAME_SIZE = 960
        # Silence en float32 (coherent avec la queue)
        silence_frame = np.zeros(FRAME_SIZE, dtype=np.float32)
        
        for _ in range(silence_frames):
            if session.cancel_flag or session.current_request_id != request_id:
                break
            await session.tts_audio_queue.put(silence_frame.copy())

    async def _wait_queue_empty(self, session: "Session", request_id: int, timeout: float = 2.0) -> None:
        """
        Attendre que la queue audio soit presque vide avant de continuer.
        Vérifie cancel_flag fréquemment pour sortir vite en cas d'interruption.
        """
        logger = logging.getLogger(__name__)
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if session.cancel_flag or session.current_request_id != request_id:
                logger.debug("wait_queue_empty: cancelled client_id=%s", session.client_id)
                break
            if session.tts_audio_queue.qsize() <= 1:
                break
            # Vérifier toutes les 5ms pour sortir vite en cas d'interruption
            await asyncio.sleep(0.005)

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

    async def _speak_state_response(
        self,
        session: "Session",
        request_id: int,
        text: str,
        interruptible: bool = True,
        emit_boundary_emotions: bool = True,
    ) -> None:
        """
        Synthétiser et envoyer une réponse TTS pour la machine à états.
        
        Args:
            session: Session WebSocket
            request_id: ID de requête
            text: Texte à synthétiser
            interruptible: Si True, l'utilisateur peut interrompre ce TTS
            emit_boundary_emotions: Si True, envoie les émotions automatiques
                de début/fin de parole ("speaking" / "idle").
        """
        logger = logging.getLogger(__name__)
        if not text or session.tts_track is None:
            return

        session.tts_playing = True
        session.reset_tts_output_state()
        session.tts_started_at = time.monotonic()
        session.tts_interruptible = interruptible  # Définir si interruptible

        if emit_boundary_emotions:
            # Envoyer l'émotion "speaking" avant la réponse
            try:
                if self.ws_service is not None:
                    await self.ws_service.send(session, {"type": "emotion", "name": "speaking"})
            except Exception:
                pass  # Ignorer silencieusement pour ne pas bloquer le TTS

        # Démarrer le scheduler
        scheduler_task = asyncio.create_task(
            self._tts_scheduler(session, request_id),
            name=f"tts-scheduler-{session.client_id}"
        )

        try:
            samples, rate = await self.tts.synthesize(text)

            if not session.cancel_flag and session.current_request_id == request_id:
                # Envoyer via queue (avec prébuffer et découpage)
                await self._emit_tts_audio(
                    session=session,
                    phrase_text=text,
                    samples=samples,
                    rate=rate,
                    client_event_type="response",
                )

                # Attendre que la queue soit presque vide
                await self._wait_queue_empty(session, request_id, timeout=2.0)

                # Flush de fin : 100ms de silence
                await self._flush_tts_queue(session, request_id, silence_frames=5)

                # Attendre que le flush soit consommé
                await asyncio.sleep(0.15)
        except Exception:
            logger.exception("TTS state response error client_id=%s", session.client_id)
        finally:
            # Arrêter le scheduler
            if not scheduler_task.done():
                scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task

            session.tts_playing = False
            session.reset_tts_output_state()
            session.tts_started_at = 0.0
            session.tts_interruptible = True  # Reset à True par défaut
            # Réinitialiser l'état VAD pour que la prochaine parole soit détectée
            session.reset_audio_buffer()
            if hasattr(session, "vad_h"):
                session.vad_h = None
            if hasattr(session, "vad_c"):
                session.vad_c = None
            if emit_boundary_emotions:
                await self._send_emotion(session, "idle")

    async def _handle_update_trip_action(
        self,
        session: "Session",
        params: dict,
    ) -> None:
        """
        Exécuter l'action update_trip depuis la machine à états.
        """
        logger = logging.getLogger(__name__)
        if self.state_machine is None:
            return

        # Récupérer le driver_serial depuis la session
        # (devrait être stocké dans la session ou le contexte)
        driver_serial = getattr(session, "driver_serial", None)
        if not driver_serial:
            logger.warning(
                "update_trip action: missing driver_serial client_id=%s",
                session.client_id,
            )
            return

        trip_id = getattr(session, "current_trip_id", None)
        if not trip_id:
            logger.warning(
                "update_trip action: missing trip_id client_id=%s",
                session.client_id,
            )
            return

        status = params.get("status", "COMPLETED")
        reason = params.get("reason")

        success = await self.state_machine.update_trip_status(
            driver_serial=driver_serial,
            trip_id=trip_id,
            status=status,
            reason=reason,
        )

        if success:
            logger.info(
                "✅ Trip updated client_id=%s trip_id=%s status=%s",
                session.client_id,
                trip_id,
                status,
            )
        else:
            logger.error(
                "❌ Trip update failed client_id=%s trip_id=%s",
                session.client_id,
                trip_id,
            )

    async def handle_external_control(
        self,
        session: "Session",
        action: str,
        extras: dict,
    ) -> None:
        """
        Gérer les événements external_control reçus du client.

        Actions supportées :
        - arrived: Le driver est arrivé sur place
        - started_navigation: Navigation démarrée
        - completed_delivery: Livraison terminée
        - photo_taken: Photo prise (response à ask_photo_event)
        - photo_not_taken: Photo non prise (response à ask_photo_event)
        """
        logger = logging.getLogger(__name__)
        logger.info(
            "📮 EXTERNAL CONTROL REÇU client_id=%s action=%s extras=%r",
            session.client_id,
            action,
            extras,
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

    async def _handle_photo_taken_action(
        self,
        session: "Session",
        photo_taken: bool,
    ) -> None:
        """
        Gérer la réponse photo_taken ou photo_not_taken.
        Appelle la state machine pour traiter la réponse.
        """
        logger = logging.getLogger(__name__)
        
        if self.state_machine is None:
            logger.warning("⚠️ State machine non disponible client_id=%s", session.client_id)
            return
        
        # Appeler le handler de la state machine
        await self.state_machine.handle_photo_response(session, photo_taken)
        await self._consume_pending_arrived(session)

    async def _handle_arrived_action(
        self,
        session: "Session",
        extras: dict,
    ) -> None:
        """
        Gérer l'action "arrived" : le driver est arrivé sur place.
        Démarre automatiquement le flux de complétion (MODE_1).
        PRIORITÉ ABSOLUE : cette question ne peut PAS être interrompue.
        """
        logger = logging.getLogger(__name__)
        trip_id = extras.get("trip_id")

        if not trip_id:
            logger.warning("⚠️ arrived action: missing trip_id client_id=%s", session.client_id)
            return

        logger.info("🚚 DRIVER ARRIVÉ client_id=%s trip_id=%s", session.client_id, trip_id)

        # Si un flow de complétion est déjà en cours pour une autre livraison,
        # on diffère l'événement "arrived" pour éviter le chevauchement.
        if self.state_machine is not None and self.state_machine.is_in_mode_1(session):
            active_trip_id = getattr(session, "current_trip_id", None)
            if active_trip_id and active_trip_id != trip_id:
                session.pending_arrived_trip_id = trip_id
                logger.info(
                    "⏸️ arrived deferred while MODE_1 active client_id=%s active_trip_id=%s pending_trip_id=%s",
                    session.client_id,
                    active_trip_id,
                    trip_id,
                )
                return

        # ⚠️ INTERROMPRE proprement tout pipeline/TTS en cours avant de démarrer
        # la state machine, afin d'éviter qu'un ancien scheduler ou une ancienne
        # réponse continue à tourner en arrière-plan.
        if session.tts_playing or session.processing_lock.locked():
            logger.info(
                "🔇 Interrupting current TTS before arrived action client_id=%s",
                session.client_id,
            )
            await self.interrupt(session, event_type="tts_stop_now")

        # Reset complet de l'état TTS
        session.tts_playing = False
        session.tts_interruptible = False  # Non interruptible pendant la question
        session.reset_tts_output_state()
        session.tts_started_at = 0.0
        session.interruption_pending = False
        session.interruption_elapsed_ms = 0.0
        session.cancel_flag = False

        # Stocker le trip_id dans la session pour la state machine
        session.current_trip_id = trip_id

        # Démarrer la machine à états (MODE_1 → STATE_1)
        if self.state_machine is not None:
            logger.info("🚀 Démarrage de la state machine pour client_id=%s", session.client_id)
            await self.state_machine.enter_mode_1(session, trip_id)

            # 🚨 CRITIQUE: Poser la question TTS SANS attendre le lock
            # On utilise _speak_text_internal directement car c'est une action prioritaire
            logger.info("🗣️ Envoi question TTS: 'Is the delivery completed?' (NON-INTERRUPTIBLE)")
            await self._speak_text_internal(session, "Is the delivery completed?", interruptible=False)
            self.llm.add_system_message( "The driver has arrived at the delivery location. Ask if the delivery is completed.")
        else:
            logger.warning("⚠️ State machine non disponible client_id=%s", session.client_id)

    async def _consume_pending_arrived(self, session: "Session") -> None:
        pending_trip_id = getattr(session, "pending_arrived_trip_id", None)
        if not pending_trip_id:
            return

        session.pending_arrived_trip_id = None
        logging.getLogger(__name__).info(
            "▶️ consuming deferred arrived client_id=%s trip_id=%s",
            session.client_id,
            pending_trip_id,
        )
        await self._handle_arrived_action(session, {"trip_id": pending_trip_id})

    async def _handle_started_navigation_action(
        self,
        session: "Session",
        extras: dict,
    ) -> None:
        """
        Gérer l'action "started_navigation" : navigation démarrée.
        """
        logger = logging.getLogger(__name__)
        trip_id = extras.get("trip_id")
        
        logger.info(
            "🗺️ Navigation started client_id=%s trip_id=%s",
            session.client_id,
            trip_id or "N/A",
        )

    async def _handle_completed_delivery_action(
        self,
        session: "Session",
        extras: dict,
    ) -> None:
        """
        Gérer l'action "completed_delivery" : livraison terminée.
        """
        logger = logging.getLogger(__name__)
        trip_id = extras.get("trip_id")
        status = extras.get("status", "COMPLETED")
        reason = extras.get("reason")
        
        if not trip_id:
            logger.warning("completed_delivery action: missing trip_id client_id=%s", session.client_id)
            return
        
        logger.info(
            "✅ Delivery completed client_id=%s trip_id=%s status=%s",
            session.client_id,
            trip_id,
            status,
        )
        
        # Mettre à jour le statut via PlanningService
        if self.state_machine is not None:
            success = await self.state_machine.update_trip_status(
                driver_serial=session.driver_serial,
                trip_id=trip_id,
                status=status,
                reason=reason,
            )
            if success:
                logger.info("✅ Trip status updated client_id=%s trip_id=%s", session.client_id, trip_id)

    def _save_debug_stt_audio(
        self,
        session: "Session",
        raw_samples: np.ndarray,
        denoised_samples: np.ndarray,
        sample_rate: int,
        *,
        utterance_id: str | None = None,
    ) -> None:
        """
        Sauvegarde brute + débruitée de l'utterance réellement envoyée au pipeline STT
        dans le flux normal WebRTC, pour comparaison A/B.
        """
        logger = logging.getLogger(__name__)

        try:
            recordings_dir = Path("assets/recordings")
            recordings_dir.mkdir(parents=True, exist_ok=True)

            utterance_id = str(utterance_id or uuid.uuid4().hex[:8])
            client_id = str(getattr(session, "client_id", "unknown")).replace("/", "_")
            prefix = f"webrtc_{client_id}_{utterance_id}"

            raw_path = recordings_dir / f"{prefix}_raw.wav"
            denoised_path = recordings_dir / f"{prefix}_denoised.wav"

            self.audio.save_wav(raw_path, np.asarray(raw_samples, dtype=np.float32), sample_rate=sample_rate)
            self.audio.save_wav(denoised_path, np.asarray(denoised_samples, dtype=np.float32), sample_rate=sample_rate)

            raw_rms = float(np.sqrt(np.mean(raw_samples * raw_samples))) if raw_samples.size else 0.0
            denoised_rms = float(np.sqrt(np.mean(denoised_samples * denoised_samples))) if denoised_samples.size else 0.0

            logger.info(
                "Saved WebRTC STT audio compare client_id=%s raw=%s denoised=%s raw_rms=%.6f denoised_rms=%.6f sr=%d",
                session.client_id,
                raw_path.name,
                denoised_path.name,
                raw_rms,
                denoised_rms,
                sample_rate,
            )
        except Exception:
            logger.exception("Failed to save WebRTC STT comparison audio client_id=%s", session.client_id)

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
