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
    _ping_task: Optional[asyncio.Task] = None  # Tâche de keep-alive WebSocket

    # ── Pipeline audio ────────────────────────────────────────────────────────
    # Buffer PCM brut accumulé entre deux silences (VAD)
    audio_buffer: list = field(default_factory=list)
    # Petit historique des chunks avant speech_start pour ne pas couper le début des mots.
    pre_speech_buffer: deque = field(default_factory=deque)
    # Chunks consécutifs > seuil en attente de confirmation avant speech_start.
    speech_start_buffer: list = field(default_factory=list)
    # Buffers debug du flux WebRTC décodé avant resampling vers 16kHz.
    decoded_audio_buffer: list = field(default_factory=list)
    decoded_pre_speech_buffer: deque = field(default_factory=deque)
    decoded_pre_speech_samples: int = 0
    decoded_sample_rate: int = 0
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
    processing_started_at: float = 0.0
    tts_started_at: float = 0.0
    # Fin du segment TTS précédent, gardée pour lisser le début du suivant.
    tts_overlap_tail: object | None = None
    tts_overlap_rate: int = 0
    active_user_message_index: Optional[int] = None
    active_user_request_id: int = 0
    active_user_text: str = ""
    interruption_pending: bool = False
    interruption_elapsed_ms: float = 0.0
    # Permet d'annuler la génération en cours
    current_request_id: int = 0
    cancel_flag: bool = False
    # Queue audio pour le scheduler TTS (frames int16 de 960 samples)
    tts_audio_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=50))
    # True si le TTS en cours peut être interrompu par l'utilisateur
    tts_interruptible: bool = True

    # ── Delivery State Machine ───────────────────────────────────────────────
    # Serial du driver (pour delivery completion flow)
    driver_serial: Optional[str] = None
    # ID du trip en cours de complétion
    current_trip_id: Optional[str] = None
    # ID d'un événement "arrived" reçu pendant qu'un flow précédent est encore actif
    pending_arrived_trip_id: Optional[str] = None

    # ── Synchronisation ───────────────────────────────────────────────────────
    # Verrou pour éviter deux traitements STT→LLM→TTS simultanés
    processing_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_request_id(self) -> int:
        self.current_request_id += 1
        return self.current_request_id

    def reset_audio_buffer(self):
        self.audio_buffer.clear()
        self.pre_speech_buffer.clear()
        self.speech_start_buffer.clear()
        self.post_roll_chunks = 0
        self.is_speaking = False
        self.silence_chunks = 0
        self.speech_chunks = 0
        # Vider la queue audio TTS
        while not self.tts_audio_queue.empty():
            try:
                self.tts_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def reset_decoded_audio_buffer(self):
        self.decoded_audio_buffer.clear()
        self.decoded_pre_speech_buffer.clear()
        self.decoded_pre_speech_samples = 0
        self.decoded_sample_rate = 0

    def reset_conversation(self):
        self.conversation_history.clear()

    def reset_tts_output_state(self):
        self.tts_overlap_tail = None
        self.tts_overlap_rate = 0

    def mark_active_user_turn(self, *, request_id: int, index: int, text: str) -> None:
        self.active_user_request_id = int(request_id)
        self.active_user_message_index = int(index)
        self.active_user_text = str(text or "").strip()

    def clear_active_user_turn(self) -> None:
        self.active_user_request_id = 0
        self.active_user_message_index = None
        self.active_user_text = ""
        self.processing_started_at = 0.0

    def reset_interruption_state(self) -> None:
        self.interruption_pending = False
        self.interruption_elapsed_ms = 0.0

    def trim_history(self, max_size: int, trim_to: int):
        if len(self.conversation_history) > max_size:
            self.conversation_history = self.conversation_history[-trim_to:]
