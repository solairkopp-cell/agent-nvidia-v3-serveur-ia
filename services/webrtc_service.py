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


logger = logging.getLogger(__name__)


# ── TTSAudioTrack ─────────────────────────────────────────────────────────────

class TTSAudioTrack(MediaStreamTrack):
    """
    AudioStreamTrack custom pour envoyer l'audio TTS généré
    vers le client WebRTC.

    aiortc appelle recv() en boucle à la fréquence d'horloge média.
    On bloque sur la queue jusqu'à ce qu'un frame soit disponible.

    Usage :
      track = TTSAudioTrack()
      pc.addTrack(track)              # avant la négociation SDP
      await track.feed(av_frame)      # depuis AgentService
    """
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._queue: asyncio.Queue = asyncio.Queue()
        self._staged: deque = deque()
        self._buffer_cond = asyncio.Condition()
        self._buffered_samples: int = 0
        self._pts: int = 0              # presentation timestamp cumulé
        self._sample_rate: int = config.SAMPLE_RATE
        self._samples_per_frame: int = max(1, int(self._sample_rate * 0.02))  # 20ms
        prebuffer_ms = max(0, int(getattr(config, "TTS_PLAYBACK_PREBUFFER_MS", 0)))
        self._prebuffer_frames: int = max(1, int(math.ceil(prebuffer_ms / 20.0))) if prebuffer_ms > 0 else 1
        self._prebuffer_timeout_sec: float = max(0.0, prebuffer_ms / 1000.0)
        self._queue_timeout_sec: float = 0.2
        self._started: bool = self._prebuffer_frames <= 1

    async def recv(self):
        """
        Appelé par aiortc pour obtenir le prochain frame audio.
        Bloque jusqu'à ce que la queue ait un frame.
        Si la queue est vide depuis trop longtemps → générer du silence.

        Retourne : av.AudioFrame
        """
        frame = await self._next_frame()

        # Normaliser pts / time_base
        if getattr(frame, "sample_rate", None) is None:
            frame.sample_rate = self._sample_rate
        if getattr(frame, "pts", None) is None:
            frame.pts = self._pts
        if getattr(frame, "time_base", None) is None:
            frame.time_base = Fraction(1, self._sample_rate)

        # Avancer l'horloge sur la base du nombre de samples du frame
        samples = getattr(frame, "samples", None)
        if isinstance(samples, int) and samples > 0:
            self._pts += samples
        else:
            self._pts += self._samples_per_frame

        return frame

    async def feed(self, frame) -> None:
        """
        Ajouter un av.AudioFrame dans la queue.
        Appelé depuis AgentService._stream_response().
        """
        await self._increase_buffered(self._frame_samples(frame))
        await self._queue.put(frame)

    async def clear(self) -> None:
        """
        Vider la queue (interruption).
        Appelé depuis AgentService.interrupt().
        """
        self._staged.clear()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._started = self._prebuffer_frames <= 1
        await self._set_buffered(0)

    def buffered_ms(self) -> float:
        return float(self._buffered_samples / float(self._sample_rate) * 1000.0)

    async def wait_until_buffer_below(self, threshold_ms: float) -> None:
        threshold = max(0, int(self._sample_rate * (max(0.0, float(threshold_ms)) / 1000.0)))
        async with self._buffer_cond:
            while self._buffered_samples > threshold:
                await self._buffer_cond.wait()

    async def _next_frame(self):
        if self._staged:
            frame = self._staged.popleft()
            await self._decrease_buffered(self._frame_samples(frame))
            return frame

        if not self._started:
            primed = await self._prime_playback()
            if primed is not None:
                return primed

        try:
            frame = await asyncio.wait_for(self._queue.get(), timeout=self._queue_timeout_sec)
            await self._decrease_buffered(self._frame_samples(frame))
            return frame
        except asyncio.TimeoutError:
            # Si le buffer se vide, repasser par une phase de prébuffer
            # pour lisser la reprise du segment suivant.
            self._started = self._prebuffer_frames <= 1
            return self._silence_frame()

    async def _prime_playback(self):
        try:
            first = await asyncio.wait_for(self._queue.get(), timeout=self._queue_timeout_sec)
        except asyncio.TimeoutError:
            return None

        self._staged.append(first)
        if self._prebuffer_frames > 1 and self._prebuffer_timeout_sec > 0:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self._prebuffer_timeout_sec
            while len(self._staged) < self._prebuffer_frames:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    self._staged.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
                except asyncio.TimeoutError:
                    break

        self._started = True
        frame = self._staged.popleft()
        await self._decrease_buffered(self._frame_samples(frame))
        return frame

    async def _increase_buffered(self, samples: int) -> None:
        if samples <= 0:
            return
        async with self._buffer_cond:
            self._buffered_samples += int(samples)
            self._buffer_cond.notify_all()

    async def _decrease_buffered(self, samples: int) -> None:
        if samples <= 0:
            return
        async with self._buffer_cond:
            self._buffered_samples = max(0, self._buffered_samples - int(samples))
            self._buffer_cond.notify_all()

    async def _set_buffered(self, samples: int) -> None:
        async with self._buffer_cond:
            self._buffered_samples = max(0, int(samples))
            self._buffer_cond.notify_all()

    def _frame_samples(self, frame) -> int:
        samples = getattr(frame, "samples", None)
        if isinstance(samples, int) and samples > 0:
            return samples
        return self._samples_per_frame

    def _silence_frame(self) -> object:
        """
        Générer un frame de silence (samples=0).
        Utilisé quand la queue est vide.
        """
        frame = av.AudioFrame(format="s16", layout="mono", samples=self._samples_per_frame)
        frame.sample_rate = self._sample_rate
        frame.pts = self._pts
        frame.time_base = Fraction(1, self._sample_rate)
        for plane in frame.planes:
            plane.update(b"\x00" * plane.buffer_size)
        return frame


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
    ):
        self.vad = vad
        self.agent = agent
        self.audio = audio
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

                if frames_seen % 50 == 0:
                    rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
                    logger.info(
                        "Audio in client_id=%s frame=%d rate=%d n=%d rms=%.4f",
                        session.client_id,
                        frames_seen,
                        rate,
                        int(samples.size),
                        rms,
                    )

                # Accumuler et découper en chunks VAD
                if buffer.size == 0:
                    buffer = samples
                else:
                    buffer = np.concatenate([buffer, samples]).astype(np.float32, copy=False)

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
                    asyncio.create_task(
                        self.agent.process_utterance_pcm(session, vad_result.audio, config.SAMPLE_RATE)
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
        Logger tous les changements d'état.
        """
        pc = session.peer
        state = getattr(pc, "connectionState", None) if pc is not None else None
        logger.info("WebRTC state client_id=%s state=%s", session.client_id, state)
        if state in ("failed", "closed"):
            await self.cleanup(session)
