"""
config.py
Centralise toutes les constantes et variables d'environnement.
"""
import os

# ── Serveur ──────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── STT ──────────────────────────────────────────────────────────────────────
WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:8080/inference")
WHISPER_TIMEOUT = int(os.getenv("WHISPER_TIMEOUT", "30"))
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr")  # ou "en", ou None (auto)

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "smollm2:1.7b-instruct-q4_K_M")
OLLAMA_CONTEXT_WINDOW = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "2048"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "150"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))

# ── TTS ──────────────────────────────────────────────────────────────────────
KOKORO_MODEL_PATH = os.getenv("KOKORO_MODEL_PATH", "/models/kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", "/models/voices-v1.0.bin")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_LANG = os.getenv("KOKORO_LANG", "en-us")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))

# ── Audio / VAD ───────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
VAD_CHUNK_MS = 32                   # ms par chunk Silero
VAD_SILENCE_THRESHOLD = 0.6         # seuil probabilité vocale
VAD_SILENCE_DURATION_MS = int(os.getenv("VAD_SILENCE_DURATION_MS", "480"))
VAD_MIN_SPEECH_MS = int(os.getenv("VAD_MIN_SPEECH_MS", "300"))
SILERO_MODEL_PATH = os.getenv(
    "SILERO_MODEL_PATH",
    "/models/silero_vad.onnx",
)

# ── WebRTC / ICE ─────────────────────────────────────────────────────────────
STUN_URL = os.getenv("STUN_URL", "stun:stun.l.google.com:19302")
TURN_URL = os.getenv("TURN_URL", "")           # optionnel
TURN_USERNAME = os.getenv("TURN_USERNAME", "")
TURN_CREDENTIAL = os.getenv("TURN_CREDENTIAL", "")

# ── Conversation ─────────────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
TRIM_TO = int(os.getenv("TRIM_TO", "30"))
