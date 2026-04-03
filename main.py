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
import base64
import logging
from pathlib import Path
import time
import uuid

import numpy as np

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
from experimental.denoise_stream import create_denoise_stream_processor
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

# Passer le ws_service au webrtc_service pour l'envoi des émotions
webrtc_service._ws_service = ws_service

# Injection des dépendances dans la state machine
state_machine._ws_service = ws_service
state_machine._agent_service = agent_service

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

# Mount static files for assets
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

@app.get("/", include_in_schema=False)
async def index():
    html = Path("web/index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/record", include_in_schema=False)
async def record_page():
    """Page d'enregistrement audio avec DeepFilterNet"""
    html = Path("web/record.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/list-recordings")
async def list_recordings():
    """Liste les enregistrements sauvegardés"""
    recordings_dir = Path("assets/recordings")
    recordings_dir.mkdir(parents=True, exist_ok=True)
    
    files = sorted(
        [f.name for f in recordings_dir.iterdir() if f.suffix in (".wav", ".webm", ".mp3")],
        reverse=True
    )
    return JSONResponse({"files": files})


@app.post("/api/save-audio-denoised")
async def save_audio_denoised(request: dict):
    """
    Sauvegarde l'audio débruité.

    Pour préserver la qualité et éviter les phrases coupées, si `raw_audio`
    est fourni, le backend applique un débruitage one-shot sur l'enregistrement
    complet avant sauvegarde.

    Request:
    {
        "audio": "<base64 encoded denoised audio>",      # optionnel
        "raw_audio": "<base64 encoded raw pcm 16kHz>"    # recommandé
    }
    """
    try:
        import wave

        raw_audio_base64 = request.get("raw_audio")
        denoised_audio_base64 = request.get("audio")

        if raw_audio_base64:
            raw_audio_bytes = base64.b64decode(raw_audio_base64)
            raw_samples = np.frombuffer(raw_audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            denoised_samples = await denoise_service.process_utterance(raw_samples, sample_rate=16000)
            audio_bytes = (np.clip(denoised_samples, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
            logger.info(
                "Received raw audio for final denoise: input=%d bytes output=%d bytes",
                len(raw_audio_bytes),
                len(audio_bytes),
            )
        elif denoised_audio_base64:
            audio_bytes = base64.b64decode(denoised_audio_base64)
            logger.info("Received streamed denoised audio: %d bytes", len(audio_bytes))
        else:
            return JSONResponse({"error": "No audio data provided"}, status_code=400)

        # Sauvegarder en WAV
        filename = f"recording_{uuid.uuid4().hex[:8]}_denoised.wav"
        recordings_dir = Path("assets/recordings")
        recordings_dir.mkdir(parents=True, exist_ok=True)
        filepath = recordings_dir / filename

        with wave.open(str(filepath), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio_bytes)

        logger.info("Saved denoised audio: %s (%s bytes)", filepath, f"{filepath.stat().st_size:,}")

        return JSONResponse({
            "filename": filename,
            "url": f"/assets/recordings/{filename}"
        })

    except Exception as e:
        logger.exception("Error saving denoised audio")
        return JSONResponse({"error": str(e)}, status_code=500)


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


@app.websocket("/ws-denoise")
async def websocket_denoise_endpoint(websocket: WebSocket):
    """
    WebSocket pour le débruitage audio en temps réel.
    
    Client envoie: {"audio": "<base64 raw pcm 16kHz>"}
    Serveur retourne: {"status": "ok", "audio": "<base64 denoised pcm>"}
    """
    from fastapi import WebSocketDisconnect
    
    await websocket.accept()
    
    processor = create_denoise_stream_processor(denoise_service)
    
    # Startup si pas déjà fait
    if not processor._ready:
        if not processor.startup():
            await websocket.send_json({"status": "error", "message": "DeepFilterNet not available"})
            await websocket.close()
            return
    
    try:
        while True:
            # Recevoir message
            data = await websocket.receive_json()
            
            if "audio" in data:
                # Traiter le chunk
                result = await processor.process_chunk(data["audio"])
                await websocket.send_json(result)
            
            elif "final" in data and data["final"]:
                # Fin d'enregistrement, traiter le buffer restant
                result = await processor.process_final()
                await websocket.send_json(result)
                processor.reset()
            
            elif "reset" in data and data["reset"]:
                # Reset le buffer
                processor.reset()
                await websocket.send_json({"status": "ok", "message": "Buffer reset"})
    
    except WebSocketDisconnect:
        logger.info("Denoise WebSocket disconnected")
    except Exception as e:
        logger.error(f"Denoise WebSocket error: {e}", exc_info=True)
        try:
            await websocket.send_json({"status": "error", "message": str(e)})
        except:
            pass


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
