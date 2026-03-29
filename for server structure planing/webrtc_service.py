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
from typing import TYPE_CHECKING, Optional

import numpy as np
from aiortc import MediaStreamTrack, RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription

import config
from models.session import Session

if TYPE_CHECKING:
    from services.vad_service import VADService
    from services.agent_service import AgentService
    from services.audio_service import AudioService


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
        self._pts: int = 0              # presentation timestamp cumulé
        self._sample_rate: int = config.SAMPLE_RATE
        self._samples_per_frame: int = 960  # 60ms @ 16kHz (standard WebRTC)

    async def recv(self):
        """
        Appelé par aiortc pour obtenir le prochain frame audio.
        Bloque jusqu'à ce que la queue ait un frame.
        Si la queue est vide depuis trop longtemps → générer du silence.

        Retourne : av.AudioFrame
        """
        raise NotImplementedError

    async def feed(self, frame) -> None:
        """
        Ajouter un av.AudioFrame dans la queue.
        Appelé depuis AgentService._stream_response().
        """
        await self._queue.put(frame)

    async def clear(self) -> None:
        """
        Vider la queue (interruption).
        Appelé depuis AgentService.interrupt().
        """
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _silence_frame(self) -> object:
        """
        Générer un frame de silence (samples=0).
        Utilisé quand la queue est vide.
        """
        raise NotImplementedError


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
        raise NotImplementedError

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
        raise NotImplementedError

    async def add_ice_candidate(self, session: Session, candidate: dict) -> None:
        """
        Ajouter un candidat ICE reçu du client.
        candidate = {"candidate": "...", "sdpMid": "...", "sdpMLineIndex": 0}
        """
        raise NotImplementedError

    async def cleanup(self, session: Session) -> None:
        """
        Fermer la connexion WebRTC et libérer les ressources.
        Appeler session.peer.close() et mettre à jour session.
        """
        raise NotImplementedError

    # ── Handlers WebRTC ───────────────────────────────────────────────────────

    async def on_track(self, session: Session, track: MediaStreamTrack) -> None:
        """
        Appelé quand une track audio arrive du client.
        Lancer _process_audio_track(session, track) comme tâche asyncio.
        Ignorer les tracks vidéo.
        """
        raise NotImplementedError

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
        raise NotImplementedError

    async def on_state_change(self, session: Session) -> None:
        """
        Appelé quand connectionstate change.
        Si "failed" ou "closed" → cleanup(session).
        Logger tous les changements d'état.
        """
        raise NotImplementedError
