import asyncio
import json
import logging
from typing import Callable, Awaitable

import numpy as np
import websockets

logger = logging.getLogger(__name__)

class PiperClientService:
    def __init__(self, uri="ws://localhost:9000/"):
        self.uri = uri
        self.ws = None
        self._audio_callback = None
        self._listen_task = None

    def set_audio_callback(self, callback: Callable[[np.ndarray], Awaitable[None]]):
        self._audio_callback = callback

    async def startup(self):
        logger.info(f"Connexion au Piper Streaming Server externe sur {self.uri}")
        await self._connect()
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def shutdown(self):
        logger.info("Fermeture du PiperClientService")
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()

    async def _connect(self):
        try:
            self.ws = await websockets.connect(self.uri)
            logger.info("WebSocket Piper connecté.")
        except Exception as e:
            logger.error(f"Erreur de connexion au serveur Piper: {e}")

    async def health_check(self) -> bool:
        return self.ws is not None

    async def _listen_loop(self):
        while True:
            if self.ws is None:
                await asyncio.sleep(1)
                await self._connect()
                continue
            
            try:
                message = await self.ws.recv()
                if isinstance(message, bytes) and len(message) >= 4:
                    # Le serveur renvoie du binaire PCM (Float32 le).
                    # Bytes 0-3: UInt32 -> N (nombre d'échantillons)
                    # Bytes 4+: Float32Array
                    samples = np.frombuffer(message[4:], dtype='<f4')
                    if self._audio_callback:
                        await self._audio_callback(samples)
            except websockets.ConnectionClosed:
                logger.warning("Connexion Piper fermée. Tentative de reconnexion...")
                self.ws = None
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur dans le listen_loop du Piper: {e}")
                self.ws = None
                await asyncio.sleep(1)

    async def _send(self, payload: dict):
        if self.ws is None:
            await self._connect()
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps(payload))
            except websockets.ConnectionClosed:
                logger.warning("Connexion Piper fermée lors de l'envoi.")
                self.ws = None
            except Exception as e:
                logger.error(f"Erreur d'envoi WebSocket Piper: {e}")
                self.ws = None

    async def interrupt(self):
        await self._send({"type": "tts_interrupt"})

    async def stream_text(self, text: str):
        if not text:
            return
        await self._send({"type": "tts_stream", "text": text})

    async def flush(self):
        await self._send({"type": "tts_stream_flush"})

    async def speak_text(self, text: str):
        if not text:
            return
        await self._send({"type": "tts", "text": text})

    async def feed_text(self, text: str):
        # Alias pour la logique de legacy bloc
        await self.speak_text(text)
