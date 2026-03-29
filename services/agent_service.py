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
            → KokoroTTSService.synthesize_stream()
            → Session.tts_track.feed(samples)

Le lock session.processing_lock garantit qu'un seul pipeline
s'exécute par session à la fois.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from models.session import Session
    from services.whisper_service import WhisperService
    from services.ollama_service import OllamaService
    from services.kokoro_tts_service import KokoroTTSService
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
        tts: "KokoroTTSService",
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
            await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False

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
            await self.interrupt(session)

        async with session.processing_lock:
            request_id = session.next_request_id()
            session.cancel_flag = False

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

        transcript = (text or "").strip()
        logger.info("STT transcript client_id=%s text_len=%d", session.client_id, len(transcript))
        if not transcript:
            if self.ws_service is not None:
                await self.ws_service.send(session, {"type": "stt_empty"})
            return

        if self.ws_service is not None:
            await self.ws_service.send_transcript(session, transcript)

        # Intent detection (optionnel)
        detected_intent = None
        if self.intent is not None:
            try:
                detected_intent = await asyncio.to_thread(self.intent.getint, transcript)
            except Exception:
                logger.exception("Intent detection error client_id=%s", session.client_id)
                detected_intent = None

            if self.ws_service is not None:
                await self.ws_service.send(
                    session,
                    {"type": "intent", "intent": detected_intent or "INCONNU"},
                )

            if _parse_bool(config.INTENT_GATE_LLM) and detected_intent and detected_intent != "INCONNU":
                return

        # Historique
        session.conversation_history.append({"role": "user", "content": transcript})

        # LLM -> TTS streaming
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

    async def interrupt(self, session: "Session") -> None:
        """
        Annuler le traitement en cours pour cette session.
        
        Actions :
          1. session.cancel_flag = True
          2. Vider la queue du TTSAudioTrack si il existe
          3. Notifier le client via WebSocket {"type": "interrupted"}
        
        Appelé par WebRTCService quand une nouvelle utterance est détectée
        pendant qu'une réponse TTS est en cours de diffusion.
        """
        session.cancel_flag = True
        if session.tts_track is not None:
            try:
                await session.tts_track.clear()
            except Exception:
                pass
        if self.ws_service is not None:
            await self.ws_service.send(session, {"type": "interrupted"})

    # ── Pipeline interne ─────────────────────────────────────────────────────

    async def _stream_response(
        self,
        session: "Session",
        user_text: str,
        request_id: int,
    ) -> str:
        """
        LLM streaming → TTS streaming → TTSAudioTrack.

        Algorithme :
          1. Créer un token_stream = OllamaService.generate_stream(user_text, history)
          2. Passer token_stream à KokoroTTSService.synthesize_stream(
               token_stream,
               cancel_check=lambda: session.cancel_flag or session.current_request_id != request_id
             )
          3. Pour chaque (phrase, samples, rate) yielded :
               - Vérifier cancel_flag + request_id
               - audio_service.array_to_av_frame(samples, rate)
               - session.tts_track.feed(av_frame)
               - Optionnel : notifier le client du texte via WebSocket
          4. Retourner le texte complet généré

        Retourne le texte complet (pour l'historique).
        """
        logger = logging.getLogger(__name__)
        if session.tts_track is None:
            return ""

        history = session.conversation_history
        token_stream = self.llm.generate_stream(user_text, history)

        full_text_parts: list[str] = []
        session.tts_playing = True
        try:
            async for phrase_text, samples, rate in self.tts.synthesize_stream(
                token_stream,
                cancel_check=lambda: session.cancel_flag or session.current_request_id != request_id,
            ):
                if session.cancel_flag or session.current_request_id != request_id:
                    break

                if phrase_text:
                    full_text_parts.append(phrase_text)
                    if self.ws_service is not None:
                        await self.ws_service.send_response_chunk(session, phrase_text)

                # Conversion -> frame et feed dans la track
                try:
                    frames = self.audio.array_to_av_frames(
                        samples,
                        source_rate=rate,
                        target_rate=config.SAMPLE_RATE,
                    )
                    if samples is not None and len(samples) > 0:
                        logger.info(
                            "TTS audio client_id=%s phrase_len=%d src_rate=%d out_rate=%d samples=%d frames=%d",
                            session.client_id,
                            len(phrase_text or ""),
                            int(rate),
                            int(config.SAMPLE_RATE),
                            int(len(samples)),
                            len(frames),
                        )
                    for frame in frames:
                        await session.tts_track.feed(frame)
                except Exception:
                    # AudioService pas encore implémenté / conversion ratée
                    logger.exception("TTS feed error client_id=%s", session.client_id)
                    break
        except Exception:
            logger.exception("Stream response error client_id=%s", session.client_id)
        finally:
            session.tts_playing = False

        return " ".join("".join(full_text_parts).split()).strip()

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def set_ws_service(self, ws_service: "WebSocketService") -> None:
        """Injection tardive pour éviter la dépendance circulaire."""
        self.ws_service = ws_service


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    v = str(value or "").strip().lower()
    return v in ("1", "true", "yes", "on")
