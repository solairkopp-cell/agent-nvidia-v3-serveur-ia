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
  5. PiperTTSService     (charge modèle ONNX)
  6. AgentService        (injection des 4 précédents)
  7. WebRTCService       (injection VAD + Agent + Audio)
  8. WebSocketService    (injection WebRTC)
  9. AgentService.set_ws_service(ws_service)  (résout dépendance circulaire)

Ordre d'arrêt (shutdown) : inverse du démarrage.
"""

from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path
import time

import numpy as np

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

import config
from logging_setup import setup_file_logging
from services.audio_service import AudioService
from services.vad_service import VADService
from services.whisper_service import WhisperService
from services.ollama_service import OllamaService
from services.intent_service import IntentService
from services.action_service import ActionService
from services.notification_service import NotificationService
from services.delivery_service import DeliveryService
from services.piper_tts_service import PiperTTSService
from services.agent_service import AgentService
from services.denoise_service import DenoiseService
from services.webrtc_service import WebRTCService
from services.websocket_service import WebSocketService
from services.delivery_state_machine import DeliveryStateMachine


# ── Logging ───────────────────────────────────────────────────────────────────
setup_file_logging(log_file_path=config.LOG_FILE_PATH, level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# ── Composition root ──────────────────────────────────────────────────────────
# Instanciés ici, injectés dans les services.

audio_service    = AudioService()
vad_service      = VADService()
whisper_service  = WhisperService()
ollama_service   = OllamaService()
intent_service   = IntentService()
action_service   = ActionService()
notification_service = NotificationService()
delivery_service = DeliveryService()
piper_service    = PiperTTSService()
denoise_service  = DenoiseService(audio=audio_service)
state_machine    = DeliveryStateMachine(intent_detector=intent_service)

agent_service    = AgentService(
    stt=whisper_service,
    llm=ollama_service,
    tts=piper_service,
    audio=audio_service,
    intent=intent_service,
    action=action_service,
    denoise=denoise_service,
    state_machine=state_machine,
)

webrtc_service   = WebRTCService(
    vad=vad_service,
    agent=agent_service,
    audio=audio_service,
)

ws_service       = WebSocketService(
    webrtc=webrtc_service,
    notification=notification_service,
)

# Résolution de la dépendance circulaire Agent ↔ WebSocket
agent_service.set_ws_service(ws_service)

# Résolution de la dépendance circulaire Notification ↔ WebSocket
notification_service.set_ws_service(ws_service)

# Injection du WebSocketService dans ActionService
action_service.set_ws_service(ws_service)

# Injection des services dans DeliveryService
delivery_service.set_notification_service(notification_service)
delivery_service.set_ws_service(ws_service)

# Enregistrement des handlers de notifications
notification_service.register_handler("identify_driver", delivery_service.identify_driver)
notification_service.register_handler("get_trips", delivery_service._handle_get_trips_wrapper)


async def _run_warmup_step(name: str, op) -> None:
    start = time.perf_counter()
    try:
        await asyncio.wait_for(op(), timeout=config.PREWARM_TIMEOUT_SEC)
        logger.info("Warmup %s ok in %.2fs", name, time.perf_counter() - start)
    except Exception:
        logger.exception("Warmup %s failed", name)


async def prewarm_services() -> None:
    """
    Préchauffer les services pour réduire la latence de la première requête.
    Les erreurs de warmup sont loggées mais ne bloquent pas le démarrage.
    """
    if not config.PREWARM_ON_STARTUP:
        logger.info("Warmup disabled")
        return

    logger.info("Warmup started")

    vad_samples = np.zeros(int(config.SAMPLE_RATE * (config.VAD_CHUNK_MS / 1000.0)), dtype=np.float32)
    stt_samples = np.zeros(int(config.SAMPLE_RATE), dtype=np.float32)

    async def _warm_vad():
        await asyncio.to_thread(vad_service.score, vad_samples)

    async def _warm_stt():
        await whisper_service.transcribe_pcm(stt_samples, config.SAMPLE_RATE)

    async def _warm_intent():
        await asyncio.to_thread(intent_service.getint, config.PREWARM_INTENT_TEXT)

    async def _warm_llm():
        await ollama_service.generate(config.PREWARM_LLM_TEXT, [])

    async def _warm_tts():
        await piper_service.synthesize(config.PREWARM_TTS_TEXT)

    for name, op in (
        ("vad", _warm_vad),
        ("stt", _warm_stt),
        ("intent", _warm_intent),
        ("llm", _warm_llm),
        ("tts", _warm_tts),
    ):
        await _run_warmup_step(name, op)

    logger.info("Warmup finished")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    await vad_service.startup()
    await whisper_service.startup()
    await ollama_service.startup()
    await intent_service.startup()
    await action_service.startup()
    await notification_service.startup()
    await delivery_service.startup()
    await state_machine.startup()
    await piper_service.startup()
    await denoise_service.startup()
    await prewarm_services()
    # AudioService et WebRTCService/WebSocketService n'ont pas de startup async

    yield  # L'application tourne ici

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await piper_service.shutdown()
    await denoise_service.shutdown()
    await delivery_service.shutdown()
    await state_machine.shutdown()
    await notification_service.shutdown()
    await action_service.shutdown()
    await intent_service.shutdown()
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

@app.get("/", include_in_schema=False)
async def index():
    html = Path("web/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


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
            "piper": true/false,
        }
    }
    """
    return {
        "status": "ok",
        "sessions": ws_service.active_sessions,
        "webrtc_peers": ws_service.active_webrtc_peers,
        "services": {
            "ws":      await ws_service.health_check(),
            "webrtc":  await webrtc_service.health_check(),
            "whisper": await whisper_service.health_check(),
            "ollama":  await ollama_service.health_check(),
            "intent":  await intent_service.health_check(),
            "action":  await action_service.health_check(),
            "notification": await notification_service.health_check(),
            "delivery": await delivery_service.health_check(),
            "state_machine": True,  # Pas de health check nécessaire
            "piper":   await piper_service.health_check(),
            "denoise": await denoise_service.health_check(),
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


# ── API Notifications ─────────────────────────────────────────────────────────

@app.post("/notifications/send/{client_id}")
async def send_notification(client_id: str, notification_type: str, data: dict | None = None):
    """
    Envoyer une notification à un client spécifique.

    - client_id: ID du client cible
    - notification_type: Type de notification (ex: "new_delivery")
    - data: Données JSON de la notification

    Retourne:
    {"sent": true/false, "message": "..."}
    """
    success = await notification_service.send_to_client(client_id, notification_type, data)
    if success:
        return {"sent": True, "message": "Notification sent"}
    else:
        return {"sent": False, "message": "Client not found"}, 404


@app.post("/notifications/broadcast")
async def broadcast_notification(notification_type: str, data: dict | None = None):
    """
    Envoyer une notification à tous les clients connectés.

    - notification_type: Type de notification
    - data: Données JSON de la notification

    Retourne:
    {"sent": true, "count": N}
    """
    await notification_service.broadcast(notification_type, data)
    return {"sent": True, "count": notification_service.ws_service.active_sessions if notification_service.ws_service else 0}


# ── Entrée ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,       # False en production
        log_level="info",
    )
