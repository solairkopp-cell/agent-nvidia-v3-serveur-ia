"""
models/session.py
État complet d'une session client.
Un objet Session par connexion WebSocket / WebRTC active.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from aiortc import RTCPeerConnection
    from fastapi import WebSocket
    from services.webrtc_service import TTSAudioTrack


@dataclass
class Session:
    # ── Identité ─────────────────────────────────────────────────────────────
    client_id: str

    # ── Transport ────────────────────────────────────────────────────────────
    websocket: "WebSocket"
    peer: Optional["RTCPeerConnection"] = None
    tts_track: Optional["TTSAudioTrack"] = None

    # ── Pipeline audio ────────────────────────────────────────────────────────
    # Buffer PCM brut accumulé entre deux silences (VAD)
    audio_buffer: list = field(default_factory=list)
    # Petit historique des chunks avant speech_start pour ne pas couper le début des mots.
    pre_speech_buffer: deque = field(default_factory=deque)
    # Nombre de chunks de post-roll déjà accumulés après la détection de fin de parole.
    post_roll_chunks: int = 0
    # True si le VAD est actuellement en phase de parole
    is_speaking: bool = False
    # Nombre de chunks de silence consécutifs depuis la fin de parole
    silence_chunks: int = 0
    # Nombre de chunks de parole accumulés (pour la durée min)
    speech_chunks: int = 0

    # ── Conversation ──────────────────────────────────────────────────────────
    # Historique messages [{role, content}] pour le LLM
    conversation_history: list = field(default_factory=list)

    # ── Contrôle TTS ─────────────────────────────────────────────────────────
    # True si le client est en train de lire du TTS
    tts_playing: bool = False
    # Permet d'annuler la génération en cours
    current_request_id: int = 0
    cancel_flag: bool = False

    # ── Synchronisation ───────────────────────────────────────────────────────
    # Verrou pour éviter deux traitements STT→LLM→TTS simultanés
    processing_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_request_id(self) -> int:
        self.current_request_id += 1
        return self.current_request_id

    def reset_audio_buffer(self):
        self.audio_buffer.clear()
        self.pre_speech_buffer.clear()
        self.post_roll_chunks = 0
        self.is_speaking = False
        self.silence_chunks = 0
        self.speech_chunks = 0

    def reset_conversation(self):
        self.conversation_history.clear()

    def trim_history(self, max_size: int, trim_to: int):
        if len(self.conversation_history) > max_size:
            self.conversation_history = self.conversation_history[-trim_to:]
