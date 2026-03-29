"""
config.py
Centralise toutes les constantes et variables d'environnement.
"""
import os

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH", "logs/server.log")

# ── Serveur ──────────────────────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ── STT ──────────────────────────────────────────────────────────────────────
# Mode STT :
# - "embedded" : faster-whisper chargé dans le même process Python (recommandé)
# - "http"     : client HTTP vers un serveur externe (ancien mode)
WHISPER_MODE = os.getenv("WHISPER_MODE", "embedded")
WHISPER_URL = os.getenv("WHISPER_URL", "http://localhost:8080/inference")  # utilisé si WHISPER_MODE="http"
WHISPER_TIMEOUT = int(os.getenv("WHISPER_TIMEOUT", "30"))                  # utilisé si WHISPER_MODE="http"
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "fr")  # ou "en", ou None (auto)

# faster-whisper (embedded)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small.en")        # ex: tiny, base, small, medium, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")       # "cuda" ou "cpu"
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
# Backend STT embarqué :
# - "whisper"        : OpenAI Whisper (PyTorch, GPU ok)
# - "faster-whisper" : faster-whisper (CTranslate2)
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "whisper")

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b-q4_K_M")
OLLAMA_CONTEXT_WINDOW = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "2048"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "150"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.md")
# Désactiver le mode "thinking" (si supporté par Ollama / modèle)
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false")

# ── Intent Detection (embeddings) ────────────────────────────────────────────
# Intentions stockées dans un CSV (colonnes : intent, example)
INTENT_CSV_PATH = os.getenv("INTENT_CSV_PATH", "intent_detection/intentions.csv")
INTENT_EMBED_MODEL = os.getenv("INTENT_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
# Intent detection peut tourner sur CPU (recommandé sur Orin pour éviter la pression VRAM).
# Valeurs: "cpu" | "cuda" | "auto"
INTENT_DEVICE = os.getenv("INTENT_DEVICE", "cuda")
INTENT_THRESHOLD = float(os.getenv("INTENT_THRESHOLD", "0.70"))
# Si true: si un intent connu est détecté, ne pas appeler le LLM (le client gère l'action)
INTENT_GATE_LLM = os.getenv("INTENT_GATE_LLM", "false")

# ── TTS ──────────────────────────────────────────────────────────────────────
KOKORO_MODEL_PATH = os.getenv("KOKORO_MODEL_PATH", "assets/models/kokoro-v1.0.onnx")
KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", "assets/models/voices-v1.0.bin")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_LANG = os.getenv("KOKORO_LANG", "en-us")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))
# Kokoro sur Orin : forcer CPU si GPU provoque des erreurs mémoire NvMap
KOKORO_DEVICE = os.getenv("KOKORO_DEVICE", "cpu")  # "cpu" ou "cuda" (selon build)

# ── Denoising ────────────────────────────────────────────────────────────────
DENOISE_ENABLED = os.getenv("DENOISE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
DENOISE_BACKEND = os.getenv("DENOISE_BACKEND", "rnnoise").strip().lower()
# Appliquer le denoise seulement sur l'audio final envoyé au STT.
# Désactivé par défaut pour privilégier la précision des commandes courtes.
DENOISE_FOR_STT = os.getenv("DENOISE_FOR_STT", "false").strip().lower() in ("1", "true", "yes", "on")

# ── Audio / VAD ───────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
VAD_CHUNK_MS = 32                   # ms par chunk Silero
VAD_SILENCE_THRESHOLD = 0.6         # seuil probabilité vocale
# Seuil de continuation (hysteresis) : avec RNNoise, garder un seuil plus bas
# aide beaucoup à ne pas casser les phrases courtes après un speech_start.
VAD_CONTINUE_THRESHOLD = float(os.getenv("VAD_CONTINUE_THRESHOLD", "0.70"))
VAD_SILENCE_DURATION_MS = int(os.getenv("VAD_SILENCE_DURATION_MS", "480"))
# Plus permissif pour laisser passer les commandes très courtes.
VAD_MIN_SPEECH_MS = int(os.getenv("VAD_MIN_SPEECH_MS", "160"))
# Garder un peu d'audio brut avant speech_start pour éviter de couper le début des mots.
VAD_PRE_ROLL_MS = int(os.getenv("VAD_PRE_ROLL_MS", "320"))
# Conserver un peu de silence après la fin détectée pour éviter les coupures trop sèches.
VAD_POST_ROLL_MS = int(os.getenv("VAD_POST_ROLL_MS", "640"))
# Garde-fou : forcer une fin d'utterance après N ms même sans silence net
VAD_MAX_UTTERANCE_MS = int(os.getenv("VAD_MAX_UTTERANCE_MS", "6000"))
SILERO_MODEL_PATH = os.getenv(
    "SILERO_MODEL_PATH",
    "assets/models/silero_vad.onnx",
)

# ── WebRTC / ICE ─────────────────────────────────────────────────────────────
STUN_URL = os.getenv("STUN_URL", "stun:stun.l.google.com:19302")
TURN_URL = os.getenv("TURN_URL", "")           # optionnel
TURN_USERNAME = os.getenv("TURN_USERNAME", "")
TURN_CREDENTIAL = os.getenv("TURN_CREDENTIAL", "")

# ── Warmup / Préchauffage ────────────────────────────────────────────────────
PREWARM_ON_STARTUP = os.getenv("PREWARM_ON_STARTUP", "true").strip().lower() in ("1", "true", "yes", "on")
PREWARM_TIMEOUT_SEC = int(os.getenv("PREWARM_TIMEOUT_SEC", "20"))
PREWARM_INTENT_TEXT = os.getenv("PREWARM_INTENT_TEXT", "bonjour")
PREWARM_LLM_TEXT = os.getenv("PREWARM_LLM_TEXT", "Reply only with ok.")
PREWARM_TTS_TEXT = os.getenv("PREWARM_TTS_TEXT", "Warmup.")

# ── Conversation ─────────────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
TRIM_TO = int(os.getenv("TRIM_TO", "30"))
