"""
main.py
Point d'entrée de l'application.

Responsabilité :
  - Instancier tous les services (composition root)
  - Démarrer / arrêter les services dans le bon ordre (lifespan)
  - Déclarer les routes FastAPI
  - Lancer Uvicorn

Ordre de démarrage (startup) :
  1. AudioService        (pas d'I/O, instanciation simple)
  2. VADService          (charge Silero ONNX)
  3. WhisperService      (crée client HTTP, health check)
  4. OllamaService       (crée client, vérifie modèle)
  5. KokoroTTSService    (charge modèle ONNX)
  6. AgentService        (injection des 4 précédents)
  7. WebRTCService       (injection VAD + Agent + Audio)
  8. WebSocketService    (injection WebRTC)
  9. AgentService.set_ws_service(ws_service)  (résout dépendance circulaire)

Ordre d'arrêt (shutdown) : inverse du démarrage.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket

import config
from services.audio_service import AudioService
from services.vad_service import VADService
from services.whisper_service import WhisperService
from services.ollama_service import OllamaService
from services.kokoro_tts_service import KokoroTTSService
from services.agent_service import AgentService
from services.webrtc_service import WebRTCService
from services.websocket_service import WebSocketService


# ── Composition root ──────────────────────────────────────────────────────────
# Instanciés ici, injectés dans les services.

audio_service    = AudioService()
vad_service      = VADService()
whisper_service  = WhisperService()
ollama_service   = OllamaService()
kokoro_service   = KokoroTTSService()

agent_service    = AgentService(
    stt=whisper_service,
    llm=ollama_service,
    tts=kokoro_service,
    audio=audio_service,
)

webrtc_service   = WebRTCService(
    vad=vad_service,
    agent=agent_service,
    audio=audio_service,
)

ws_service       = WebSocketService(webrtc=webrtc_service)

# Résolution de la dépendance circulaire Agent ↔ WebSocket
agent_service.set_ws_service(ws_service)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    await vad_service.startup()
    await whisper_service.startup()
    await ollama_service.startup()
    await kokoro_service.startup()
    # AudioService et WebRTCService/WebSocketService n'ont pas de startup async

    yield  # L'application tourne ici

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await kokoro_service.shutdown()
    await ollama_service.shutdown()
    await whisper_service.shutdown()
    await vad_service.shutdown()


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Voice Agent Server",
    description="WebRTC + WebSocket voice agent (STT → LLM → TTS)",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    Health check global.
    Retourne l'état de chaque service dépendant.
    {
        "status": "ok",
        "sessions": N,
        "services": {
            "whisper": true/false,
            "ollama": true/false,
            "kokoro": true/false,
        }
    }
    """
    return {
        "status": "ok",
        "sessions": ws_service.active_sessions,
        "services": {
            "whisper": await whisper_service.health_check(),
            "ollama":  await ollama_service.health_check(),
            "kokoro":  await kokoro_service.health_check(),
        }
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Point d'entrée WebSocket unique.
    1. ws_service.connect(websocket) → Session
    2. ws_service.listen(session)    → boucle messages (bloquant)
    La déconnexion est gérée à l'intérieur de listen().
    """
    session = await ws_service.connect(websocket)
    await ws_service.listen(session)


# ── Entrée ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,       # False en production
        log_level="info",
    )
