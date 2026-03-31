"""
services/tts_media_player.py
Générateur de flux audio pour TTS via MediaPlayer.

Crée un pipe FIFO que aiortc.MediaPlayer peut lire.
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

try:
    from aiortc.contrib.media import MediaPlayer  # type: ignore
except Exception as exc:
    raise RuntimeError("aiortc is required") from exc

import config

logger = logging.getLogger(__name__)


class TTSMediaPlayerSource:
    """
    Crée un flux audio temporaire que MediaPlayer peut lire.
    
    Usage:
        source = TTSMediaPlayerSource()
        await source.start()
        player = MediaPlayer(source.pipe_path, format='s16le', options={
            'ar': '22050',
            'ac': '1',
        })
        # ... utiliser player.audio ...
        await source.write(pcm_bytes)  # Écrire des frames TTS
        await source.stop()
    """
    
    def __init__(self):
        self._pipe_path: Optional[str] = None
        self._pipe_file = None
        self._started = False
        self._lock = asyncio.Lock()
        
    async def start(self) -> str:
        """Créer le pipe FIFO et retourner son chemin."""
        if self._started:
            return self._pipe_path
            
        # Créer un pipe temporaire
        self._pipe_path = tempfile.mktemp(prefix="tts_pipe_")
        os.mkfifo(self._pipe_path)
        
        # Ouvrir en écriture (non-bloquant)
        # Note: l'ouverture en écriture bloque jusqu'à ce qu'un lecteur ouvre
        self._pipe_file = open(self._pipe_path, 'wb', buffering=0)
        self._started = True
        
        logger.info("TTS pipe created: %s", self._pipe_path)
        return self._pipe_path
        
    async def write(self, pcm_bytes: bytes) -> bool:
        """
        Écrire des données PCM dans le pipe.
        
        Parameters
            pcm_bytes: Données audio PCM (s16le, mono, 22050Hz)
            
        Returns
            True si écrit avec succès, False si pipe fermé
        """
        if not self._started or self._pipe_file is None:
            return False
            
        try:
            async with self._lock:
                self._pipe_file.write(pcm_bytes)
                self._pipe_file.flush()
            return True
        except (BrokenPipeError, IOError) as e:
            logger.warning("TTS pipe broken: %s", e)
            return False
            
    async def stop(self) -> None:
        """Fermer le pipe et nettoyer."""
        self._started = False
        
        if self._pipe_file is not None:
            try:
                self._pipe_file.close()
            except Exception:
                pass
            self._pipe_file = None
            
        if self._pipe_path and Path(self._pipe_path).exists():
            try:
                os.unlink(self._pipe_path)
            except Exception:
                pass
                
        logger.info("TTS pipe closed")


class TTSMediaPlayer:
    """
    Wrapper qui combine TTSMediaPlayerSource + MediaPlayer.
    
    Usage:
        tts_player = TTSMediaPlayer()
        await tts_player.start()
        
        # Obtenir le MediaPlayer à passer à WebRTC
        player = tts_player.get_player()
        
        # Écrire de l'audio TTS
        await tts_player.write(pcm_bytes)
        
        # Arrêt
        await tts_player.stop()
    """
    
    def __init__(self):
        self._source = TTSMediaPlayerSource()
        self._player: Optional[MediaPlayer] = None
        self._started = False
        
    async def start(self) -> None:
        """Démarrer le flux TTS."""
        pipe_path = await self._source.start()
        
        # Créer MediaPlayer qui lit le pipe
        # Format: PCM s16le, mono, 22050 Hz (format natif de Piper)
        self._player = MediaPlayer(
            file=pipe_path,
            format='s16le',
            options={
                'ar': str(config.AUDIO_OUTPUT_SAMPLE_RATE),  # 22050
                'ac': '1',  # mono
            },
            loop=False,
        )
        
        self._started = True
        logger.info("TTSMediaPlayer started")
        
    def get_player(self) -> Optional[MediaPlayer]:
        """Retourner le MediaPlayer pour l'ajouter au peer WebRTC."""
        return self._player
        
    async def write(self, pcm_bytes: bytes) -> bool:
        """Écrire des données PCM TTS dans le flux."""
        if not self._started:
            return False
        return await self._source.write(pcm_bytes)
        
    async def stop(self) -> None:
        """Arrêter le lecteur TTS."""
        if self._player is not None:
            try:
                await self._player.stop()
            except Exception:
                pass
            self._player = None
            
        await self._source.stop()
        self._started = False
        logger.info("TTSMediaPlayer stopped")
