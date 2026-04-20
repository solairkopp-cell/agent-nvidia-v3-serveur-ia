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
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")  # ou "en", ou None (auto)

# faster-whisper (embedded)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")        # ex: tiny, base, small, medium, large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")       # "cpu" pour maximiser la stabilité Jetson
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # "int8" pour les modèles quantifiés (ex: small.en), "float16" pour les modèles non quantifiés (ex: medium)
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))
# Backend STT embarqué :
# - "whisper"        : OpenAI Whisper (PyTorch, GPU ok)
# - "faster-whisper" : faster-whisper (CTranslate2, beaucoup plus léger sur Jetson)
WHISPER_BACKEND = os.getenv("WHISPER_BACKEND", "faster-whisper")

PIPER_BIN_PATH = os.getenv("PIPER_BIN_PATH", "/home/server/piper/piper/piper")

# ── LLM ──────────────────────────────────────────────────────────────────────
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:8080")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "Rytle:latest")
OLLAMA_CONTEXT_WINDOW = int(os.getenv("OLLAMA_CONTEXT_WINDOW", "1024"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "50"))
OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.7"))
OLLAMA_REPEAT_PENALTY = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.4"))
OLLAMA_STOP = _parse_env_words("OLLAMA_STOP", "<|im_start|>,<|im_end|>")
OLLAMA_PRESENCE_PENALTY = float(os.getenv("OLLAMA_PRESENCE_PENALTY", "0.0"))
OLLAMA_TOP_K = int(os.getenv("OLLAMA_TOP_K", "20"))
OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.95"))
SYSTEM_PROMPT_PATH = os.getenv("SYSTEM_PROMPT_PATH", "system_prompt.md")
# Désactiver le mode "thinking" (si supporté par Ollama / modèle)
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false")

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
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "assets/models/en_US-hfc_female-medium.onnx")
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "assets/models/en_US-hfc_female-medium.onnx.json")

# ── TTS Common Settings ──────────────────────────────────────────────────────
# Streaming TTS : commencer à parler avant la fin de la phrase complète.
# Augmenté à 8 mots pour des phrases plus naturelles et moins de coupures
TTS_STREAM_WORD_CHUNK_SIZE = int(os.getenv("TTS_STREAM_WORD_CHUNK_SIZE", "8"))
# Fondu/crossfade entre segments pour éviter les coupures sèches (100ms)
TTS_SEGMENT_OVERLAP_MS = float(os.getenv("TTS_SEGMENT_OVERLAP_MS", "100"))
# Buffer segments TTS : 5 est un bon compromis vitesse/fluidité
TTS_SEGMENT_QUEUE_MAXSIZE = int(os.getenv("TTS_SEGMENT_QUEUE_MAXSIZE", "5"))
# Petit tampon de lecture avant de lancer le son.
# 1500ms = buffer confortable pour Internet (fluide mais ~1.5s de latence)
TTS_PLAYBACK_PREBUFFER_MS = int(os.getenv("TTS_PLAYBACK_PREBUFFER_MS", "1500"))
# Déclencher la synthèse/livraison du segment suivant quand il reste peu d'audio
# en file côté serveur.
TTS_BUFFER_LOW_WATERMARK_MS = int(os.getenv("TTS_BUFFER_LOW_WATERMARK_MS", "1200"))
# Intervalle entre les frames audio WebRTC (ms).
# IMPORTANT : doit correspondre à la durée réelle des frames (voir webrtc_service.py)
# 10ms = latence minimale, 20ms = compromis, 40ms = ralenti
TTS_FRAME_INTERVAL_MS = int(os.getenv("TTS_FRAME_INTERVAL_MS", "10"))
# Trim silence : seuil très bas pour éviter de couper
TTS_TRIM_SILENCE_THRESHOLD = float(os.getenv("TTS_TRIM_SILENCE_THRESHOLD", "0.0001"))
TTS_TRIM_SILENCE_PAD_MS = int(os.getenv("TTS_TRIM_SILENCE_PAD_MS", "80"))
TTS_TRIM_MIN_SILENCE_MS = int(os.getenv("TTS_TRIM_MIN_SILENCE_MS", "150"))
TTS_TRIM_LEADING = os.getenv("TTS_TRIM_LEADING", "false").strip().lower() in ("1", "true", "yes", "on")
# Désactivé pour éviter de couper les fins de phrases
TTS_TRIM_TRAILING = os.getenv("TTS_TRIM_TRAILING", "false").strip().lower() in ("1", "true", "yes", "on")

# ── Denoising ────────────────────────────────────────────────────────────────
# Denoise global sur l'audio entrant.
# Mettre "false" pour désactiver le débruitage (audio brut)
DENOISE_ENABLED = os.getenv("DENOISE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
DENOISE_BACKEND = os.getenv("DENOISE_BACKEND", "deepfilternet").strip().lower()
# IMPORTANT:
# - False (défaut) = VAD sur audio brut, denoise seulement sur l'utterance finale
#   avant STT / sauvegarde → latence plus faible
# - True = denoise chunk par chunk avant VAD → plus propre mais plus lent
DENOISE_BEFORE_VAD = os.getenv("DENOISE_BEFORE_VAD", "false").strip().lower() in ("1", "true", "yes", "on")
# Contrôle séparément le débruitage juste avant STT.
# False (défaut) garde un pipeline simple côté serveur :
#   decode -> mono/16k/float32 -> VAD -> Whisper
# True réactive le denoise utterance-level avant transcription.
DENOISE_FOR_STT = os.getenv("DENOISE_FOR_STT", "false").strip().lower() in ("1", "true", "yes", "on")
# Sauvegarde optionnelle d'un WAV debug du flux WebRTC décodé avant
# le resampling serveur vers 16kHz. Utile pour diagnostiquer les
# limitations de bande passante amont (Android/WebRTC/codec).
SAVE_WEBRTC_NATIVE_DEBUG = os.getenv("SAVE_WEBRTC_NATIVE_DEBUG", "true").strip().lower() in ("1", "true", "yes", "on")

# ── Audio / VAD ───────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
# 48kHz = standard WebRTC/Opus (évite le resampling interne métallique)
AUDIO_OUTPUT_SAMPLE_RATE = int(os.getenv("AUDIO_OUTPUT_SAMPLE_RATE", "48000"))  # 48kHz = Opus native
VAD_CHUNK_MS = 32                   # ms par chunk Silero
VAD_SILENCE_THRESHOLD = float(os.getenv("VAD_SILENCE_THRESHOLD", "0.85"))  # seuil probabilité vocale
# Demander plusieurs chunks consécutifs avant speech_start réduit les faux positifs
# sur bruit impulsif / souffle, sans ajouter beaucoup de latence.
VAD_START_TRIGGER_CHUNKS = int(os.getenv("VAD_START_TRIGGER_CHUNKS", "2"))
# Seuil de continuation (hysteresis) : avec RNNoise, garder un seuil plus bas
# aide beaucoup à ne pas casser les phrases courtes après un speech_start.
VAD_CONTINUE_THRESHOLD = float(os.getenv("VAD_CONTINUE_THRESHOLD", "0.5"))
# Réduire le délai de silence pour une réponse plus nerveuse.
VAD_SILENCE_DURATION_MS = int(os.getenv("VAD_SILENCE_DURATION_MS", "250"))
# Plus permissif pour laisser passer les commandes très courtes.
VAD_MIN_SPEECH_MS = int(os.getenv("VAD_MIN_SPEECH_MS", "160"))
# Garder moins d'audio brut avant speech_start (réduction de buffer).
VAD_PRE_ROLL_MS = int(os.getenv("VAD_PRE_ROLL_MS", "400"))
# Réduire le silence post-roll pour éviter de traîner sur la fin.
VAD_POST_ROLL_MS = int(os.getenv("VAD_POST_ROLL_MS", "300"))
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
PREWARM_LLM_TEXT = os.getenv("PREWARM_LLM_TEXT", "hello what's your name?")
PREWARM_TTS_TEXT = os.getenv("PREWARM_TTS_TEXT", "Warmup.")

# ── Conversation ─────────────────────────────────────────────────────────────
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "3"))
TRIM_TO = int(os.getenv("TRIM_TO", "30"))
