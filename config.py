"""
config.py
Centralise toutes les constantes et variables d'environnement.
"""
import os


def _parse_env_words(name: str, default: str) -> tuple[str, ...]:
    raw = os.getenv(name, default)
    return tuple(word.strip() for word in raw.split(",") if word.strip())

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
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")        # ex: tiny, base, small, medium, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")       # "cpu" pour maximiser la stabilité Jetson
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
# Backend STT embarqué :
# - "whisper"        : OpenAI Whisper (PyTorch, GPU ok)
# - "faster-whisper" : faster-whisper (CTranslate2, beaucoup plus léger sur Jetson)
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "faster-whisper")

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b-q4_K_M")
OLLAMA_CONTEXT_WINDOW = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "2048"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "150"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.6"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.0"))
OLLAMA_STOP = _parse_env_words("OLLAMA_STOP", "<|im_start|>,<|im_end|>")
OLLAMA_PRESENCE_PENALTY = float(os.getenv("OLLAMA_PRESENCE_PENALTY", "0.0"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "20"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.95"))
SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.md")
# Désactiver le mode "thinking" (si supporté par Ollama / modèle)
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false")

# ── Intent Detection (embeddings) ────────────────────────────────────────────
# Intentions stockées dans un CSV (colonnes : intent, example)
INTENT_CSV_PATH = os.getenv("INTENT_CSV_PATH", "intent_detection/intentions.csv")
INTENT_EMBED_MODEL = os.getenv("INTENT_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
# Intent detection sur Orin : forcer CPU pour économiser la VRAM.
INTENT_DEVICE = os.getenv("INTENT_DEVICE", "cpu")
INTENT_THRESHOLD = float(os.getenv("INTENT_THRESHOLD", "0.70"))
INTENT_EMBED_LOCAL_DIR = os.getenv("INTENT_EMBED_LOCAL_DIR", "")
INTENT_EMBED_CACHE_DIR = os.getenv("INTENT_EMBED_CACHE_DIR", "")
INTENT_EMBED_DOWNLOAD_ON_STARTUP = os.getenv("INTENT_EMBED_DOWNLOAD_ON_STARTUP", "false").strip().lower() in ("1", "true", "yes", "on")
# Si true: si un intent connu est détecté, ne pas appeler le LLM (le client gère l'action)
INTENT_GATE_LLM = os.getenv("INTENT_GATE_LLM", "false")

# ── Interruptions / Barge-in ────────────────────────────────────────────────
INTERRUPTION_SHORT_THRESHOLD_MS = float(os.getenv("INTERRUPTION_SHORT_THRESHOLD_MS", "1000"))
INTERRUPTION_WORDS_EN = _parse_env_words(
    "INTERRUPTION_WORDS_EN",
    "no,stop,wait,cancel,forget,never mind",
)
CONTINUATION_WORDS_EN = _parse_env_words(
    "CONTINUATION_WORDS_EN",
    "also,and,plus,additionally,actually,wait and",
)

# ── Piper TTS ──────────────────────────────────────────────────────────────────
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "assets/models/en_US-danny-low.onnx")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "assets/models/en_US-danny-low.onnx.json")

# ── TTS Common Settings ──────────────────────────────────────────────────────
# Streaming TTS : commencer à parler avant la fin de la phrase complète.
# Sur Orin Nano, on peut descendre à 4 mots sans perdre trop de fluidité.
TTS_STREAM_WORD_CHUNK_SIZE = int(os.getenv("TTS_STREAM_WORD_CHUNK_SIZE", "4"))
# Fondu/crossfade léger entre segments. Accepte les décimales.
TTS_SEGMENT_OVERLAP_MS = float(os.getenv("TTS_SEGMENT_OVERLAP_MS", "0.1"))
TTS_SEGMENT_QUEUE_MAXSIZE = int(os.getenv("TTS_SEGMENT_QUEUE_MAXSIZE", "3"))
# Petit tampon de lecture avant de lancer le son.
TTS_PLAYBACK_PREBUFFER_MS = int(os.getenv("TTS_PLAYBACK_PREBUFFER_MS", "200"))
# Déclencher la synthèse/livraison du segment suivant quand il reste peu d'audio
# en file côté serveur.
TTS_BUFFER_LOW_WATERMARK_MS = int(os.getenv("TTS_BUFFER_LOW_WATERMARK_MS", "500"))
TTS_TRIM_SILENCE_THRESHOLD = float(os.getenv("TTS_TRIM_SILENCE_THRESHOLD", "0.001"))
TTS_TRIM_SILENCE_PAD_MS = int(os.getenv("TTS_TRIM_SILENCE_PAD_MS", "48"))
TTS_TRIM_MIN_SILENCE_MS = int(os.getenv("TTS_TRIM_MIN_SILENCE_MS", "80"))
TTS_TRIM_LEADING = os.getenv("TTS_TRIM_LEADING", "false").strip().lower() in ("1", "true", "yes", "on")
TTS_TRIM_TRAILING = os.getenv("TTS_TRIM_TRAILING", "true").strip().lower() in ("1", "true", "yes", "on")

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
# Réduire le délai de silence pour une réponse plus nerveuse.
VAD_SILENCE_DURATION_MS = int(os.getenv("VAD_SILENCE_DURATION_MS", "300"))
# Plus permissif pour laisser passer les commandes très courtes.
VAD_MIN_SPEECH_MS = int(os.getenv("VAD_MIN_SPEECH_MS", "160"))
# Garder moins d'audio brut avant speech_start (réduction de buffer).
VAD_PRE_ROLL_MS = int(os.getenv("VAD_PRE_ROLL_MS", "240"))
# Réduire le silence post-roll pour éviter de traîner sur la fin.
VAD_POST_ROLL_MS = int(os.getenv("VAD_POST_ROLL_MS", "200"))
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
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "6"))
TRIM_TO = int(os.getenv("TRIM_TO", "30"))
