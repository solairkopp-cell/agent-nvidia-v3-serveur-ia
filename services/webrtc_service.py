"""
services/webrtc_service.py
Gestion des connexions WebRTC (aiortc).

Responsabilité :
  - Créer et gérer les RTCPeerConnection par session
  - Gérer la négociation SDP (offer → answer)
  - Gérer les candidats ICE
  - Recevoir les frames audio entrants → VAD → AgentService
  - Envoyer l'audio TTS généré vers le client via TTSAudioTrack

Dépend de :
  - VADService   : pour scorer chaque chunk audio
  - AgentService : pour traiter les utterances complètes
  - AudioService : pour les conversions de format

TTSAudioTrack est défini ici car il est étroitement lié à aiortc.
"""
from __future__ import annotations

import asyncio
from collections import deque
import logging
import math
from fractions import Fraction
from typing import TYPE_CHECKING

import numpy as np

try:
    from aiortc import (
        MediaStreamTrack,
        RTCConfiguration,
        RTCIceServer,
        RTCPeerConnection,
        RTCSessionDescription,
    )
    from aiortc import RTCIceCandidate  # type: ignore
    from aiortc.mediastreams import MediaStreamError  # type: ignore
except Exception as exc:  # pragma: no cover
    raise RuntimeError("aiortc is required to use WebRTCService. Install requirements.txt.") from exc

try:
    import av  # type: ignore
except Exception as exc:  # pragma: no cover
    raise RuntimeError("PyAV (package 'av') is required to use WebRTCService.") from exc

import config
from models.session import Session

if TYPE_CHECKING:
    from services.vad_service import VADService
    from services.agent_service import AgentService
    from services.audio_service import AudioService
    from services.websocket_service import WebSocketService


logger = logging.getLogger(__name__)


# ── TTSAudioTrack ─────────────────────────────────────────────────────────────

class TTSAudioTrack(MediaStreamTrack):
    """
    AudioStreamTrack ultra-simple pour TTS.
    Le buffer WebRTC du navigateur gère la lecture fluide.
    """
    kind = "audio"

    def __init__(self):
        super().__init__()
        # Queue pour stocker les frames audio TTS
        self._queue: asyncio.Queue = asyncio.Queue()
        self._pts: int = 0
        self._sample_rate: int = 48000  # WebRTC/Opus native sample rate
        # 20ms = standard WebRTC/Opus
        self._samples_per_frame: int = 960  # int(48000 * 20 / 1000) = 960

    async def recv(self):
        """
        Appelé par aiortc ~50 fois par seconde.
        Bloque jusqu'à ce qu'un frame soit disponible.
        """
        frame = await self._queue.get()

        # Normaliser sample_rate / time_base
        if getattr(frame, "sample_rate", None) is None:
            frame.sample_rate = self._sample_rate
        if getattr(frame, "time_base", None) is None:
            frame.time_base = Fraction(1, self._sample_rate)

        # Set PTS si pas déjà défini (frames venant de array_to_av_frame n'ont pas de PTS)
        if getattr(frame, "pts", None) is None:
            frame.pts = self._pts

        # Avancer l'horloge pour le PROCHAIN frame
        samples = getattr(frame, "samples", None)
        if isinstance(samples, int) and samples > 0:
            self._pts += samples
        else:
            self._pts += self._samples_per_frame

        return frame

    async def feed(self, frame) -> None:
        """Ajouter un frame à la queue."""
        await self._queue.put(frame)

    async def clear(self) -> None:
        """Vider la queue (interruption)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


# ── WebRTCService ─────────────────────────────────────────────────────────────

class WebRTCService:
    """
    Singleton. Injecté dans WebSocketService.
    """

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
        self._rtc_config = self._build_rtc_config()

    # ── Configuration ─────────────────────────────────────────────────────────

    def _build_rtc_config(self) -> RTCConfiguration:
        """
        Construire RTCConfiguration avec les serveurs ICE depuis config.
        Inclure STUN (obligatoire) et TURN si configuré.
        """
        servers = [RTCIceServer(urls=config.STUN_URL)]
        if config.TURN_URL:
            servers.append(RTCIceServer(
                urls=config.TURN_URL,
                username=config.TURN_USERNAME,
                credential=config.TURN_CREDENTIAL,
            ))
        return RTCConfiguration(iceServers=servers)

    async def health_check(self) -> bool:
        """
        Health check local: True si le service est instancié et que la config RTC est prête.
        """
        return self._rtc_config is not None

    # ── Lifecycle session ─────────────────────────────────────────────────────

    async def create_peer(self, session: Session) -> RTCPeerConnection:
        """
        Créer un RTCPeerConnection pour cette session.

        Actions :
          1. Créer pc = RTCPeerConnection(self._rtc_config)
          2. Créer tts_track = TTSAudioTrack()
          3. pc.addTrack(tts_track)  ← AVANT la négociation SDP
          4. session.peer = pc
          5. session.tts_track = tts_track
          6. Enregistrer les handlers :
               @pc.on("track")        → on_track(session, track)
               @pc.on("connectionstatechange") → on_state_change(session)
               @pc.on("iceconnectionstatechange") → logger

        Retourner pc.
        """
        if session.peer is not None:
            return session.peer

        pc = RTCPeerConnection(self._rtc_config)
        tts_track = TTSAudioTrack()
        pc.addTrack(tts_track)

        session.peer = pc
        session.tts_track = tts_track

        @pc.on("track")
        def _on_track(track):  # pragma: no cover (runtime only)
            asyncio.create_task(self.on_track(session, track))

        @pc.on("connectionstatechange")
        def _on_state_change():  # pragma: no cover (runtime only)
            asyncio.create_task(self.on_state_change(session))

        @pc.on("iceconnectionstatechange")
        def _on_ice_state_change():  # pragma: no cover (runtime only)
            try:
                logger.info(
                    "ICE state client_id=%s state=%s",
                    session.client_id,
                    getattr(pc, "iceConnectionState", None),
                )
            except Exception:
                return

        @pc.on("icecandidate")
        def _on_icecandidate(candidate):  # pragma: no cover (runtime only)
            async def _send():
                try:
                    if candidate is None:
                        await session.websocket.send_json({"type": "ice", "candidate": None})
                        return
                    cand_sdp = getattr(candidate, "to_sdp", None)
                    candidate_str = cand_sdp() if callable(cand_sdp) else str(candidate)
                    await session.websocket.send_json(
                        {
                            "type": "ice",
                            "candidate": {
                                "candidate": candidate_str,
                                "sdpMid": getattr(candidate, "sdpMid", None),
                                "sdpMLineIndex": getattr(candidate, "sdpMLineIndex", None),
                            },
                        }
                    )
                except Exception:
                    return

            asyncio.create_task(_send())

        logger.info("WebRTC peer created client_id=%s", session.client_id)
        return pc

    async def handle_offer(self, session: Session, sdp: str) -> str:
        """
        Traiter une offre SDP reçue du client mobile.

        Étapes :
          1. create_peer(session)
          2. await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
          3. answer = await pc.createAnswer()
          4. await pc.setLocalDescription(answer)
          5. Retourner pc.localDescription.sdp

        Retourne : SDP answer (str) à renvoyer au client via WebSocket.
        """
        pc = await self.create_peer(session)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return pc.localDescription.sdp

    async def add_ice_candidate(self, session: Session, candidate: dict) -> None:
        """
        Ajouter un candidat ICE reçu du client.
        candidate = {"candidate": "...", "sdpMid": "...", "sdpMLineIndex": 0}
        """
        pc = session.peer
        if pc is None:
            return

        candidate_str = candidate.get("candidate")
        if not isinstance(candidate_str, str) or not candidate_str.strip():
            return

        # Parsing best-effort : privilégier aiortc.sdp helpers si disponibles.
        ice = None
        try:
            from aiortc.sdp import candidate_from_sdp  # type: ignore

            ice = candidate_from_sdp(candidate_str)
            ice.sdpMid = candidate.get("sdpMid")
            ice.sdpMLineIndex = candidate.get("sdpMLineIndex")
        except Exception:
            # Fallback : tenter de passer un RTCIceCandidate minimal si possible.
            try:
                ice = RTCIceCandidate(
                    component=1,
                    foundation="0",
                    ip="0.0.0.0",
                    port=9,
                    priority=0,
                    protocol="udp",
                    type="host",
                    sdpMid=candidate.get("sdpMid"),
                    sdpMLineIndex=candidate.get("sdpMLineIndex"),
                )
            except Exception:
                ice = None

        await pc.addIceCandidate(ice)

    async def cleanup(self, session: Session) -> None:
        """
        Fermer la connexion WebRTC et libérer les ressources.
        Appeler session.peer.close() et mettre à jour session.
        """
        pc = session.peer
        session.peer = None
        tts_track = session.tts_track
        session.tts_track = None

        try:
            if tts_track is not None:
                tts_track.stop()
        except Exception:
            pass

        try:
            if pc is not None:
                await pc.close()
        except Exception:
            logger.exception("Error closing peer client_id=%s", session.client_id)

        session.reset_audio_buffer()
        session.reset_tts_output_state()
        session.tts_playing = False
        logger.info("WebRTC cleaned up client_id=%s", session.client_id)

    # ── Handlers WebRTC ───────────────────────────────────────────────────────

    async def on_track(self, session: Session, track: MediaStreamTrack) -> None:
        """
        Appelé quand une track audio arrive du client.
        Lancer _process_audio_track(session, track) comme tâche asyncio.
        Ignorer les tracks vidéo.
        """
        if track.kind != "audio":
            return
        logger.info("Audio track received client_id=%s", session.client_id)
        asyncio.create_task(self._process_audio_track(session, track))

    async def _process_audio_track(self, session: Session, track: MediaStreamTrack) -> None:
        """
        Boucle principale de réception audio.

        Pour chaque frame reçue :
          1. frame = await track.recv()
          2. samples = audio_service.array_from_av_frame(frame)
          3. Si sample_rate != 16kHz → resample
          4. Découper en chunks de VAD_CHUNK_SAMPLES
          5. Pour chaque chunk → vad.process_chunk(session, chunk)
          6. Si VADResult.type == "utterance_end" :
               - await agent.interrupt(session) si tts_playing
               - asyncio.create_task(agent.process_utterance(session, wav_bytes))

        La boucle tourne jusqu'à ce que la track se termine
        ou que la connexion soit coupée.
        """
        chunk_samples = int(config.SAMPLE_RATE * (config.VAD_CHUNK_MS / 1000.0))
        pre_roll_chunks = max(0, int(math.ceil(max(0, config.VAD_PRE_ROLL_MS) / config.VAD_CHUNK_MS)))
        buffer: np.ndarray = np.array([], dtype=np.float32)
        frames_seen = 0
        chunks_seen = 0

        try:
            while True:
                frame = await track.recv()
                frames_seen += 1

                # Conversion robuste via PyAV vers s16/mono/16k -> float32 [-1, 1].
                samples = self.audio.av_frame_to_array(frame, target_rate=config.SAMPLE_RATE)
                rate = config.SAMPLE_RATE

                # Optionnel: débruitage en amont du VAD.
                # Désactivé par défaut car DeepFilterNet chunk-par-chunk ajoute
                # une latence perceptible sur la détection de parole.
                denoised_samples = samples
                denoise_service = getattr(self.agent, "denoise", None)
                if getattr(config, "DENOISE_BEFORE_VAD", False) and denoise_service is not None:
                    try:
                        processed = await denoise_service.process(samples, sample_rate=rate)
                        if getattr(processed, "size", 0):
                            denoised_samples = processed.astype(np.float32, copy=False)
                    except Exception:
                        logger.exception("Realtime denoise before VAD failed client_id=%s", session.client_id)

                # Accumuler et découper en chunks VAD
                if buffer.size == 0:
                    buffer = denoised_samples
                else:
                    buffer = np.concatenate([buffer, denoised_samples]).astype(np.float32, copy=False)

                while buffer.size >= chunk_samples and chunk_samples > 0:
                    chunk = buffer[:chunk_samples]
                    buffer = buffer[chunk_samples:]
                    chunks_seen += 1

                    vad_result = self.vad.process_chunk(session, chunk)
                    if vad_result.type == "speech_start":
                        added = self._prepend_pre_roll(session)
                        if added > 0:
                            logger.info(
                                "VAD pre_roll client_id=%s samples=%d",
                                session.client_id,
                                added,
                            )
                    elif not session.is_speaking:
                        self._remember_pre_roll(session, chunk, pre_roll_chunks)

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
                        try:
                            await session.websocket.send_json(
                                {"type": "vad", "event": "speech_start", "p": vad_result.speech_prob}
                            )
                        except Exception:
                            pass
                    if getattr(vad_result, "ignored_short", False):
                        logger.info(
                            "VAD short_utterance_ignored client_id=%s speech_chunks=%d",
                            session.client_id,
                            session.speech_chunks,
                        )
                        try:
                            await session.websocket.send_json(
                                {"type": "vad", "event": "short_utterance_ignored", "p": vad_result.speech_prob}
                            )
                        except Exception:
                            pass
                    if vad_result.type != "utterance_end":
                        continue

                    if vad_result.audio is None or vad_result.audio.size == 0:
                        continue
                    logger.info("Utterance end client_id=%s samples=%d", session.client_id, vad_result.audio.size)
                    try:
                        await session.websocket.send_json(
                            {"type": "vad", "event": "utterance_end", "samples": int(vad_result.audio.size)}
                        )
                    except Exception:
                        pass

                    # Interruption si un pipeline est déjà en cours
                    if session.processing_lock.locked() and not session.cancel_flag:
                        await self.agent.interrupt(session)

                    # PCM direct -> STT (recommandé)
                    # Sera traité après que le lock soit libéré
                    asyncio.create_task(
                        self.agent.process_utterance_pcm(
                            session,
                            vad_result.audio,
                            config.SAMPLE_RATE,
                            apply_denoise=True,
                        )
                    )

        except MediaStreamError:
            # Normal : la track se termine (peer fermé / renegociation / stop micro).
            logger.info("Audio track ended client_id=%s", session.client_id)
            return
        except Exception:
            logger.exception("Audio track processing error client_id=%s", session.client_id)
            return

    def _remember_pre_roll(self, session: Session, chunk: np.ndarray, max_chunks: int) -> None:
        if max_chunks <= 0:
            return
        session.pre_speech_buffer.append(np.asarray(chunk, dtype=np.float32).copy())
        while len(session.pre_speech_buffer) > max_chunks:
            session.pre_speech_buffer.popleft()

    def _prepend_pre_roll(self, session: Session) -> int:
        if not session.pre_speech_buffer:
            return 0
        pre_roll = list(session.pre_speech_buffer)
        session.pre_speech_buffer.clear()
        session.audio_buffer = pre_roll + session.audio_buffer
        return int(sum(int(chunk.size) for chunk in pre_roll))

    async def on_state_change(self, session: Session) -> None:
        """
        Appelé quand connectionstate change.
        Si "failed" ou "closed" → cleanup(session).
        Si "connected" → envoyer le résumé vocal en attente (delivery_service).
        Logger tous les changements d'état.
        """
        pc = session.peer
        state = getattr(pc, "connectionState", None) if pc is not None else None
        logger.info("WebRTC state client_id=%s state=%s", session.client_id, state)
        
        if state == "connected":
            # WebRTC prêt → envoyer le résumé vocal en attente si disponible
            pending_summary = getattr(session, "_pending_voice_summary", None)
            if pending_summary is not None:
                logger.info(
                    "🔊 Sending pending voice summary client_id=%s",
                    session.client_id,
                )
                try:
                    trips = pending_summary.get("trips", [])
                    driver_name = pending_summary.get("driver_name", "Driver")
                    no_trips = pending_summary.get("no_trips", False)
                    voice_message = pending_summary.get("voice_message")
                    
                    if no_trips and voice_message:
                        # Cas "no trips" - utiliser le message pré-construit
                        # Envoyer l'émotion greeting avant le message vocal
                        try:
                            await self._ws_service.send(session, {"type": "emotion", "name": "greeting"})
                            logger.info("😊 Emotion greeting sent client_id=%s", session.client_id)
                        except Exception as e:
                            logger.error("Could not send emotion greeting: %s", e)

                        if self.agent is not None:
                            await self.agent.speak_text(session, voice_message)
                    elif trips and len(trips) > 0:
                        # Cas avec trips - construire le message
                        first_trip = trips[0]
                        client_name = getattr(first_trip, 'client_name', None) or getattr(first_trip, 'get_client_name', lambda: None)()
                        package_info = getattr(first_trip, 'package_info', None) or getattr(first_trip, 'get_package_info', lambda: None)()

                        if client_name and package_info:
                            summary_text = (
                                f"Hello {driver_name}, you have {len(trips)} trips. "
                                f"The first one is a {package_info} for {client_name}. "
                                f"Have a great day."
                            )
                        elif client_name:
                            summary_text = (
                                f"Hello {driver_name}, you have {len(trips)} trips. "
                                f"The first one is for {client_name}. "
                                f"Have a great day."
                            )
                        else:
                            summary_text = f"Hello {driver_name}, you have {len(trips)} trips. Have a great day."

                        # Envoyer l'émotion greeting avant le message vocal
                        try:
                            await self._ws_service.send(session, {"type": "emotion", "name": "greeting"})
                            logger.info("😊 Emotion greeting sent client_id=%s", session.client_id)
                        except Exception as e:
                            logger.error("Could not send emotion greeting: %s", e)

                        if self.agent is not None:
                            await self.agent.speak_text(session, summary_text)
                except Exception as e:
                    logger.exception("Error sending pending voice summary: %s", e)
                finally:
                    # Nettoyer le pending
                    session._pending_voice_summary = None
        
        if state in ("failed", "closed"):
            await self.cleanup(session)
