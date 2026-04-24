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
  7. WebSocketAudioService (transport audio WebSocket)
  8. WebSocketService      (session + messages)
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
from services.notification_service import NotificationService
from services.delivery_service import DeliveryService
from services.piper_client_service import PiperClientService
from services.agent_service import AgentService
from services.denoise_service import DenoiseService
from experimental.denoise_stream import create_denoise_stream_processor
from services.ws_audio_service import WebSocketAudioService
from services.websocket_service import WebSocketService
from services.delivery_state_machine import DeliveryStateMachine
from routers.test_audio_router import router as test_audio_router


# ── Logging ───────────────────────────────────────────────────────────────────
setup_file_logging(log_file_path=config.LOG_FILE_PATH, level=config.LOG_LEVEL)
logger = logging.getLogger(__name__)

# ── Composition root ──────────────────────────────────────────────────────────
# Instanciés ici, injectés dans les services.

audio_service    = AudioService()
vad_service      = VADService()
whisper_service  = WhisperService()
ollama_service   = OllamaService()
notification_service = NotificationService()
delivery_service = DeliveryService()
piper_service    = PiperClientService()
denoise_service  = DenoiseService(audio=audio_service)
state_machine    = DeliveryStateMachine()

agent_service    = AgentService(
    stt=whisper_service,
    llm=ollama_service,
    tts=piper_service,
    audio=audio_service,
    denoise=denoise_service,
    state_machine=state_machine,
)

audio_stream_service = WebSocketAudioService(
    vad=vad_service,
    agent=agent_service,
    audio=audio_service,
)

ws_service       = WebSocketService(
    audio_stream=audio_stream_service,
    notification=notification_service,
)

# Passer le ws_service au service audio pour l'envoi des émotions
audio_stream_service._ws_service = ws_service

# Injection des dépendances dans la state machine
state_machine._ws_service = ws_service
state_machine._agent_service = agent_service

# Résolution de la dépendance circulaire Agent ↔ WebSocket
agent_service.set_ws_service(ws_service)
ollama_service.set_ws_service(ws_service)

# Résolution de la dépendance circulaire Notification ↔ WebSocket
notification_service.set_ws_service(ws_service)

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

    async def _warm_llm():
        await ollama_service.chat(config.PREWARM_LLM_TEXT, history=[])

    async def _warm_tts():
        async for _ in piper_service.synthesize_stream(config.PREWARM_TTS_TEXT):
            pass

    for name, op in (
        ("vad", _warm_vad),
        ("stt", _warm_stt),
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
    await notification_service.startup()
    await delivery_service.startup()
    await state_machine.startup()
    await piper_service.startup()
    await denoise_service.startup()
    await prewarm_services()
    # AudioService, WebSocketAudioService et WebSocketService n'ont pas de startup async

    yield  # L'application tourne ici

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await piper_service.shutdown()
    await denoise_service.shutdown()
    await delivery_service.shutdown()
    await state_machine.shutdown()
    await notification_service.shutdown()
    await ollama_service.shutdown()
    await whisper_service.shutdown()
    await vad_service.shutdown()


# ── Application ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Voice Agent Server",
    description="WebSocket voice agent (STT → LLM → TTS)",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static files for assets
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# ── Test audio router (collecte données débruitage) ───────────────────────────
app.include_router(test_audio_router)

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
    Sauvegarde l'audio débruité + métriques comparatives.

    Si `raw_audio` est fourni, le backend :
      - sauvegarde le brut
      - applique le denoise one-shot
      - sauvegarde le résultat débruité
      - retourne des métriques simples avant/après

    Request:
    {
        "audio": "<base64 encoded denoised audio>",      # optionnel
        "raw_audio": "<base64 encoded raw pcm 16kHz>"    # recommandé
    }
    """
    try:
        import wave

        def _pcm16_to_float32(audio_bytes: bytes) -> np.ndarray:
            return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        def _float32_to_pcm16(samples: np.ndarray) -> bytes:
            clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
            return (clipped * 32767.0).astype(np.int16).tobytes()

        def _audio_metrics(samples: np.ndarray) -> dict:
            samples = np.asarray(samples, dtype=np.float32).reshape(-1)
            if samples.size == 0:
                return {"samples": 0, "duration_ms": 0, "rms": 0.0, "peak": 0.0}
            rms = float(np.sqrt(np.mean(samples * samples)))
            peak = float(np.max(np.abs(samples)))
            duration_ms = int(samples.size / 16000 * 1000)
            return {
                "samples": int(samples.size),
                "duration_ms": duration_ms,
                "rms": round(rms, 6),
                "peak": round(peak, 6),
            }

        def _write_wav(path: Path, audio_bytes: bytes) -> None:
            with wave.open(str(path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_bytes)

        raw_audio_base64 = request.get("raw_audio")
        denoised_audio_base64 = request.get("audio")

        recordings_dir = Path("assets/recordings")
        recordings_dir.mkdir(parents=True, exist_ok=True)
        recording_id = uuid.uuid4().hex[:8]

        raw_filename = None
        raw_url = None
        raw_metrics = None

        if raw_audio_base64:
            raw_audio_bytes = base64.b64decode(raw_audio_base64)
            raw_samples = _pcm16_to_float32(raw_audio_bytes)
            denoised_samples = await denoise_service.process_utterance(raw_samples, sample_rate=16000)
            audio_bytes = _float32_to_pcm16(denoised_samples)

            raw_metrics = _audio_metrics(raw_samples)
            denoised_metrics = _audio_metrics(denoised_samples)

            raw_filename = f"recording_{recording_id}_raw.wav"
            raw_filepath = recordings_dir / raw_filename
            _write_wav(raw_filepath, raw_audio_bytes)
            raw_url = f"/assets/recordings/{raw_filename}"

            logger.info(
                "Denoise compare id=%s raw_rms=%.6f denoised_rms=%.6f raw_peak=%.6f denoised_peak=%.6f raw_ms=%d denoised_ms=%d",
                recording_id,
                raw_metrics["rms"],
                denoised_metrics["rms"],
                raw_metrics["peak"],
                denoised_metrics["peak"],
                raw_metrics["duration_ms"],
                denoised_metrics["duration_ms"],
            )
            logger.info(
                "Received raw audio for final denoise: id=%s input=%d bytes output=%d bytes",
                recording_id,
                len(raw_audio_bytes),
                len(audio_bytes),
            )
        elif denoised_audio_base64:
            audio_bytes = base64.b64decode(denoised_audio_base64)
            denoised_samples = _pcm16_to_float32(audio_bytes)
            denoised_metrics = _audio_metrics(denoised_samples)
            logger.info("Received streamed denoised audio: %d bytes", len(audio_bytes))
        else:
            return JSONResponse({"error": "No audio data provided"}, status_code=400)

        denoised_filename = f"recording_{recording_id}_denoised.wav"
        denoised_filepath = recordings_dir / denoised_filename
        _write_wav(denoised_filepath, audio_bytes)

        logger.info(
            "Saved denoised audio: %s (%s bytes)",
            denoised_filepath,
            f"{denoised_filepath.stat().st_size:,}",
        )
        if raw_filename is not None:
            logger.info("Saved raw reference audio: %s", recordings_dir / raw_filename)

        return JSONResponse({
            "id": recording_id,
            "filename": denoised_filename,
            "url": f"/assets/recordings/{denoised_filename}",
            "raw_filename": raw_filename,
            "raw_url": raw_url,
            "metrics": {
                "raw": raw_metrics,
                "denoised": denoised_metrics,
            },
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
        "audio_streams": ws_service.active_audio_streams,
        "services": {
            "ws":      await ws_service.health_check(),
            "audio_stream": await audio_stream_service.health_check(),
            "whisper": await whisper_service.health_check(),
            "notification": await notification_service.health_check(),
            "delivery": await delivery_service.health_check(),
            "state_machine": True,  # Pas de health check nécessaire
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
