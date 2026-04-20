# aiserver

**aiserver** is a complete AI voice assistant server, designed to handle real-time conversations via WebSocket. It integrates a full pipeline from audio reception to speech synthesis with delivery management capabilities.

---

## 🚀 Features

1. **Real-time Audio**: Receives and sends audio via **WebSocket**
2. **Voice Activity Detection**: Detects speech using **Silero VAD**
3. **Audio Denoising**: Cleans audio with **DeepFilterNet** (streaming or utterance-level)
4. **Speech-to-Text**: Transcribes speech with **Whisper** (embedded or HTTP mode)
5. **Intent Detection**: Classifies user intentions using embeddings
6. **Smart Actions**: Executes known intents locally without LLM (navigation, deliveries, etc.)
7. **LLM Responses**: Generates intelligent responses via **Ollama** (Qwen3, Llama, etc.)
8. **Text-to-Speech**: Synthesizes responses with **Piper TTS** or **Kokoro TTS**
9. **Delivery Management**: Complete state machine for delivery tracking and completion
10. **Notifications**: Real-time push notifications to connected clients
11. **Barge-in**: Full interruption system allowing users to cut off the AI while speaking

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client (Browser)                           │
│                       Audio WebSocket                               │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        WebSocket Service                            │
│              Session Management + Message Routing                   │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Audio Stream Service                             │
│              Audio Track Handling + VAD Detection                   │
└────────┬──────────────┬──────────────────────┬──────────────────────┘
         │              │                      │
         ▼              ▼                      ▼
┌──────────────┐ ┌──────────────┐    ┌──────────────────┐
│ VAD Service  │ │ Audio Service│    │ Denoise Service  │
│  (Silero)    │ │  (PCM 16kHz) │    │ (DeepFilterNet)  │
└──────┬───────┘ └──────┬───────┘    └────────┬─────────┘
       │                │                     │
       └────────────────┼─────────────────────┘
                        ▼
              ┌──────────────────┐
              │  Whisper Service │
              │   (STT / Text)   │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Intent Service   │
              │ (Embeddings)     │
              └────────┬─────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
┌─────────────────┐       ┌──────────────────┐
│ Action Service  │       │  Agent Service   │
│ (Known Intents) │       │  (LLM / Ollama)  │
└────────┬────────┘       └────────┬─────────┘
         │                         │
         │              ┌──────────┴──────────┐
         │              │                     │
         │              ▼                     ▼
         │      ┌──────────────┐    ┌────────────────┐
         │      │ Piper TTS    │    │ Kokoro TTS     │
         │      │ (High Qual.) │    │ (Fast/Light)   │
         │      └──────────────┘    └────────────────┘
         │              │                     │
         └──────────────┼─────────────────────┘
                        ▼
              ┌──────────────────┐
              │ TTS Media Player │
              │ (PCM stream)     │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  Delivery State  │
              │    Machine       │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Notification Svc │
              │  (Push to client)│
              └──────────────────┘
```

---

## 🗂️ Project Structure

```
aiserver/
├── main.py                  # Entry point (FastAPI + Uvicorn)
├── config.py                # Centralized configuration (env vars)
├── system_prompt.md         # System prompt for the AI (Rytle)
├── requirements.txt         # Python dependencies
├── logging_setup.py         # Logging configuration
│
├── services/                # Main services
│   ├── agent_service.py     # Main orchestrator (STT → LLM → TTS)
│   ├── ws_audio_service.py  # WebSocket audio streaming
│   ├── websocket_service.py # WebSocket session management
│   ├── vad_service.py       # Voice Activity Detection (Silero ONNX)
│   ├── denoise_service.py   # Audio denoising (DeepFilterNet)
│   ├── audio_service.py     # Audio utilities (resampling, format conversion)
│   ├── whisper_service.py   # Speech-to-Text (faster-whisper or HTTP)
│   ├── ollama_service.py    # LLM inference via Ollama
│   ├── piper_tts_service.py # Text-to-Speech (Piper)
│   ├── tts_utils.py         # TTS text segmentation utilities
│   ├── notification_service.py  # Real-time push notifications
│   ├── delivery_service.py  # Delivery/trip management
│   └── delivery_state_machine.py  # Delivery completion workflow
│
├── experimental/            # Experimental features
│   └── denoise_stream.py    # Real-time denoising via WebSocket
│
├── models/                  # Data models
│   └── session.py           # Session model (state, interruption)
│
├── web/                     # Web interface
│   ├── index.html           # Main voice assistant page
│   └── record.html          # Audio recording page with DeepFilterNet
│
├── assets/                  # Static assets
│   ├── models/              # ONNX models (TTS, VAD, etc.)
│   └── recordings/          # Saved audio recordings
│
├── tests/                   # Unit tests
│   ├── test_agent_service.py
│   ├── test_audio_service.py
│   ├── test_denoise_service.py
│   ├── test_ollama_service.py
│   ├── test_piper_service.py
│   ├── test_vad_service.py
│   └── test_ws_audio_service.py
│
├── documentations/          # Additional documentation
│   ├── state_machine.md     # Delivery state machine docs
│   └── AUDIO_CONTINUITY_FIX.md
│
└── logs/                    # Log files
```

---

## 🔧 Technologies Used

| Technology | Role |
|---|---|
| [Whisper / faster-whisper](https://github.com/openai/whisper) | Speech-to-Text (STT) |
| [Ollama](https://ollama.com/) | Local LLM inference (Qwen3, Llama, etc.) |
| [Piper TTS](https://github.com/rhasspy/piper) | High-quality Text-to-Speech |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Voice Activity Detection |
| [DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) | Audio denoising |
| [websockets](https://websockets.readthedocs.io/) | WebSocket communication |
| [FastAPI](https://fastapi.tiangolo.com/) | Web framework |
| [Sentence Transformers](https://www.sbert.net/) | Intent detection embeddings |

---

## ⚙️ Installation

```bash
# Clone the repository
git clone https://github.com/vivien-azonnoudo2002/aiserver.git
cd aiserver

# Install dependencies
pip install -r requirements.txt

# Download required models (see Models section below)
```

### Prerequisites

- **Python 3.10+**
- **Ollama** running locally (default: `http://localhost:8080`)
- **ONNX Models**: VAD, TTS (see Models section)

---

## ▶️ Launch

```bash
python main.py
```

The server starts on `http://0.0.0.0:8000` by default.

**Web interfaces:**
- Main assistant: `http://localhost:8000/`
- Recording page: `http://localhost:8000/record`

---

## 🧪 Tests

```bash
pytest tests/
```

---

## 📡 API Reference

### WebSocket Endpoints

#### `POST /ws` - Main Voice Session
Primary WebSocket endpoint for voice conversations.
- **Protocol**: PCM16 audio + JSON/binary WebSocket messages
- **Messages**: STT transcripts, TTS audio chunks, intent events, interruptions

#### `POST /ws-denoise` - Real-time Denoising
WebSocket for streaming audio denoising.
- **Input**: `{"audio": "<base64 PCM 16kHz>"}`
- **Output**: `{"status": "ok", "audio": "<base64 denoised>"}`
- **Use case**: Live denoising during recording

### HTTP API

#### `GET /health` - Health Check
Returns status of all services:
```json
{
  "status": "ok",
  "sessions": 2,
  "audio_streams": 1,
  "services": {
    "ws": true,
    "audio_stream": true,
    "whisper": true,
    "ollama": true,
    "piper": true,
    "denoise": true,
    ...
  }
}
```

#### `GET /api/list-recordings` - List Recordings
Returns saved audio recordings:
```json
{
  "files": ["recording_abc123_denoised.wav", ...]
}
```

#### `POST /api/save-audio-denoised` - Save Denoised Audio
Saves denoised audio with comparative metrics:
```json
{
  "audio": "<base64 denoised>",
  "raw_audio": "<base64 raw PCM>"  // optional, triggers comparison
}
```
**Response:**
```json
{
  "id": "abc123",
  "filename": "recording_abc123_denoised.wav",
  "url": "/assets/recordings/recording_abc123_denoised.wav",
  "raw_url": "/assets/recordings/recording_abc123_raw.wav",
  "metrics": {
    "raw": {"rms": 0.15, "peak": 0.95, "duration_ms": 3200},
    "denoised": {"rms": 0.18, "peak": 0.85, "duration_ms": 3200}
  }
}
```

#### `POST /notifications/send/{client_id}` - Send Notification
Push notification to specific client:
- **client_id**: Target client identifier
- **notification_type**: Type (e.g., "new_delivery")
- **data**: JSON payload

#### `POST /notifications/broadcast` - Broadcast
Send notification to all connected clients.

---

## 🎯 Delivery State Machine

The delivery state machine manages delivery completion workflows.

### Overview

**Two operational modes:**
- **MODE_0 (Normal)**: STT → Intent Detection → Known/Unknown → TTS/LLM
- **MODE_1 (Delivery Completion)**: STT → Normalize → Pattern matching → Action

### States (MODE_1)

| State | Name | Description |
|-------|------|-------------|
| `STATE_1` | ASK_COMPLETION | "Is the delivery completed?" |
| `STATE_2` | ASK_REASON | "Can you tell me why?" |
| `STATE_4` | COMPLETE | Update trip status |
| `STATE_5` | EXIT | Return to MODE_0 |
| `STATE_6` | ASK_PHOTO | Request photo evidence |

### Workflow

```
Driver identified
    ↓
Trips retrieved
    ↓
MODE_0: Normal conversation
    ↓
[Delivery completion triggered]
    ↓
MODE_1: STATE_1 (Ask completion status)
    ↓
If yes → STATE_4 (Complete) → STATE_5 (Exit)
If no  → STATE_2 (Ask reason) → STATE_6 (Ask photo) → STATE_4 → STATE_5
```

**Full documentation**: See [documentations/state_machine.md](documentations/state_machine.md)

---

## 🔊 Text-to-Speech (TTS)

The server uses **Piper TTS** for speech synthesis.

### Piper TTS (High Quality)

| Parameter | Value |
|-----------|-------|
| **Model** | `en_US-hfc_female-medium.onnx` (default) |
| **Language** | English (US) 🇺🇸 |
| **Voice** | HFC Female |
| **Quality** | Medium-High |
| **Sample Rate** | 22050 Hz |

### TTS Configuration

In `config.py`, set:
```bash
# For Piper
PIPER_MODEL_PATH="assets/models/en_US-hfc_female-medium.onnx"
PIPER_CONFIG_PATH="assets/models/en_US-hfc_female-medium.onnx.json"

```

---

## 🛑 Barge-in / Interruption System

The server implements a complete interruption system allowing users to cut off the AI while it's speaking.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. User speaks while TTS is playing                             │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. VAD detects speech_start (32ms chunks)                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. agent.on_user_speech_start()                                 │
│    - Calculate elapsed time (elapsed_ms)                        │
│    - Set interruption_pending=True                              │
│    - Call interrupt()                                           │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. interrupt()                                                  │
│    - cancel_flag=True → cancel current pipeline                 │
│    - tts_track.clear() → empty TTS queue                        │
│    - Send {"type": "tts_stop_now"} to client                    │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. _decide_interruption_mode()                                  │
│    - continuation → merge with old message                      │
│    - interruption → replace old message                         │
└─────────────────────────────────────────────────────────────────┘
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERRUPTION_SHORT_THRESHOLD_MS` | 1000 | Time threshold for short interruptions |
| `INTERRUPTION_WORDS_EN` | `no,stop,wait,cancel,forget,never mind` | Interruption trigger words |
| `CONTINUATION_WORDS_EN` | `also,and,plus,additionally,actually,wait and` | Continuation words |

### Decision Logic

```python
if elapsed_ms < 1000ms:
    if interruption_word:
        return "interruption"
    if continuation_word:
        return "continuation"
    return "continuation"  # Default
else:
    if continuation_word:
        return "continuation"
    return "interruption"  # Default
```

### Modes

| Mode | Behavior |
|------|----------|
| **interruption** | Previous message deleted, new turn |
| **continuation** | New text merged with active user message |

### WebSocket Events

| Type | Direction | Description |
|------|-----------|-------------|
| `vad: speech_start` | Server → Client | Speech detection start |
| `interruption_decision` | Server → Client | Decision (continuation/interruption) with elapsed_ms |
| `tts_stop_now` | Server → Client | Immediate TTS stop |
| `interrupted` | Server → Client | Interruption notification |

---

## 🎙️ Audio Denoising

### DeepFilterNet

The server uses **DeepFilterNet** for audio denoising, replacing the older RNNoise approach.

### Modes

| Mode | Description | Latency | Quality |
|------|-------------|---------|---------|
| **Utterance-level** | Denoise after VAD end, before STT | Low | High |
| **Streaming** | Real-time chunk denoising before VAD | Higher | Highest |
| **Disabled** (default for STT path) | Raw audio passthrough | Lowest | Raw |

### Configuration

```bash
# Enable/disable denoising
DENOISE_ENABLED=true

# Backend
DENOISE_BACKEND=deepfilternet

# Denoise before VAD (streaming mode)
DENOISE_BEFORE_VAD=false  # Default: denoise after VAD

# Denoise final utterance before STT
DENOISE_FOR_STT=false

# Experimental streaming denoise endpoint
# Connect to: ws://localhost:8000/ws-denoise
```

### Streaming Denoise WebSocket

**Endpoint**: `ws://localhost:8000/ws-denoise`

**Messages:**
- **Input**: `{"audio": "<base64 PCM 16kHz>"}`
- **Output**: `{"status": "ok", "audio": "<base64 denoised>"}`
- **Final**: `{"final": true}` - Process remaining buffer
- **Reset**: `{"reset": true}` - Clear buffer

---

## 🔧 Configuration

All configuration is centralized in `config.py` via environment variables.

### Server

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Port number |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE_PATH` | `logs/server.log` | Log file path |

### STT (Whisper)

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODE` | `embedded` | `embedded` or `http` |
| `WHISPER_BACKEND` | `faster-whisper` | `whisper` or `faster-whisper` |
| `WHISPER_MODEL` | `small.en` | Model size (tiny, base, small, medium, large-v3) |
| `WHISPER_DEVICE` | `cuda` | `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | `int8` (quantized) or `float16` |
| `WHISPER_LANGUAGE` | `en` | Language code or `None` (auto) |

### LLM (Ollama)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:8080` | Ollama server URL |
| `OLLAMA_MODEL` | `smollm2:360m` | Model name |
| `OLLAMA_CONTEXT_WINDOW` | `1024` | Context window size |
| `OLLAMA_NUM_PREDICT` | `50` | Max tokens to generate |
| `OLLAMA_TEMPERATURE` | `0.7` | Sampling temperature |
| `OLLAMA_THINK` | `false` | Disable thinking mode |

### Audio / VAD

| Variable | Default | Description |
|----------|---------|-------------|
| `SAMPLE_RATE` | `16000` | Input sample rate |
| `AUDIO_OUTPUT_SAMPLE_RATE` | `48000` | Output sample rate (Opus native) |
| `VAD_CHUNK_MS` | `32` | VAD chunk size |
| `VAD_SILENCE_THRESHOLD` | `0.8` | Voice probability threshold |
| `VAD_CONTINUE_THRESHOLD` | `0.5` | Continuation hysteresis |
| `VAD_SILENCE_DURATION_MS` | `250` | Silence before utterance end |
| `VAD_MIN_SPEECH_MS` | `160` | Minimum speech duration |
| `VAD_PRE_ROLL_MS` | `400` | Audio buffer before speech |
| `VAD_POST_ROLL_MS` | `300` | Audio buffer after speech |
| `VAD_MAX_UTTERANCE_MS` | `6000` | Force utterance end |

### TTS

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_STREAM_WORD_CHUNK_SIZE` | `8` | Words before streaming |
| `TTS_SEGMENT_OVERLAP_MS` | `100` | Crossfade between segments |
| `TTS_SEGMENT_QUEUE_MAXSIZE` | `5` | Segment buffer |
| `TTS_PLAYBACK_PREBUFFER_MS` | `1500` | Buffer before playing |
| `TTS_BUFFER_LOW_WATERMARK_MS` | `1200` | Trigger next synthesis |
| `TTS_FRAME_INTERVAL_MS` | `10` | Audio frame interval |
| `TTS_TRIM_SILENCE_THRESHOLD` | `0.0001` | Silence detection threshold |
| `TTS_TRIM_SILENCE_PAD_MS` | `80` | Padding before silence |
| `TTS_TRIM_MIN_SILENCE_MS` | `150` | Minimum silence gap |

### Warmup

| Variable | Default | Description |
|----------|---------|-------------|
| `PREWARM_ON_STARTUP` | `true` | Enable warmup |
| `PREWARM_TIMEOUT_SEC` | `20` | Warmup timeout |
| `PREWARM_LLM_TEXT` | `hello what's your name?` | Warmup LLM |
| `PREWARM_TTS_TEXT` | `Warmup.` | Warmup TTS |

---

## 📥 Download Models

### Required Models

After installation, download the ONNX models for TTS and VAD.

#### 1. Piper TTS Voices

```bash
cd /home/server/aiserver
mkdir -p assets/models

# English voice (default) - Medium Quality
wget -O assets/models/en_US-hfc_female-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx

wget -O assets/models/en_US-hfc_female-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json

```

#### 2. Silero VAD

```bash
# Download Silero VAD model
wget -O assets/models/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
```

#### 3. Verify Models

```bash
ls -lh assets/models/
```

**Expected output:**
```
-rw-r--r-- 1 user user 60M  Apr 02 10:00 en_US-hfc_female-medium.onnx
-rw-r--r-- 1 user user 2.5K Apr 02 10:00 en_US-hfc_female-medium.onnx.json
-rw-r--r-- 1 user user 20M  Apr 02 10:01 en_US-danny-low.onnx
-rw-r--r-- 1 user user 1.8K Apr 02 10:01 en_US-danny-low.onnx.json
-rw-r--r-- 1 user user 2.2M Apr 02 10:02 silero_vad.onnx
```

---

### Recommended Piper Voices by Language

| Language | Voice | Quality | Size | Link |
|----------|-------|---------|------|------|
| 🇺🇸 English | `en_US-hfc_female-medium` | Medium | ~60 MB | [Download](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/hfc_female/medium) |
| 🇺🇸 English | `en_US-danny-low` | Low | ~20 MB | [Download](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/danny/low) |
| 🇫🇷 French | `fr_FR-siwis-medium` | Medium | ~60 MB | [Download](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium) |
| 🇩🇪 German | `de_DE-thorsten-medium` | Medium | ~60 MB | [Download](https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium) |
| 🇪🇸 Spanish | `es_ES-davefx-medium` | Medium | ~60 MB | [Download](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium) |

---

### Automatic Download Script

Create a `download_models.sh` script:

```bash
#!/bin/bash
# download_models.sh - Downloads all required models

set -e

MODEL_DIR="assets/models"
mkdir -p "$MODEL_DIR"

echo "📥 Downloading models..."

# Piper TTS - English Medium
echo "🔊 en_US-hfc_female-medium..."
wget -q --show-progress -O "$MODEL_DIR/en_US-hfc_female-medium.onnx" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx
wget -q --show-progress -O "$MODEL_DIR/en_US-hfc_female-medium.onnx.json" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx.json

# Silero VAD
echo "🎤 Silero VAD..."
wget -q --show-progress -O "$MODEL_DIR/silero_vad.onnx" \
  https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx

echo "✅ All models downloaded to $MODEL_DIR"
ls -lh "$MODEL_DIR"
```

**Usage:**
```bash
chmod +x download_models.sh
./download_models.sh
```

---

## 🧠 AI Persona: Rytle

The server uses **Rytle** as its AI persona for delivery assistance.

**Characteristics:**
- **Role**: Professional delivery assistant AI
- **Style**: Friendly, calm, and efficient
- **Communication**: Direct and concise (max 2-3 sentences)
- **Behavior**: No emojis, no filler, no preamble
- **Language**: English

**System prompt**: See [system_prompt.md](system_prompt.md)

---

## 📚 Additional Documentation

| Document | Description |
|----------|-------------|
| [state_machine.md](documentations/state_machine.md) | Delivery state machine workflow |
| [AUDIO_CONTINUITY_FIX.md](documentations/AUDIO_CONTINUITY_FIX.md) | Audio continuity improvements |

---

## 🚀 Services Lifecycle

### Startup Order

1. **VAD Service** - Loads Silero ONNX model
2. **Whisper Service** - Initializes STT (embedded or HTTP)
3. **Ollama Service** - Connects to Ollama, verifies model
4. **Intent Service** - Loads embedding model
5. **Action Service** - Registers known intents
6. **Notification Service** - Sets up WebSocket handlers
7. **Delivery Service** - Initializes delivery management
8. **State Machine** - Delivery workflow engine
9. **Piper/Kokoro TTS** - Loads TTS models
10. **Denoise Service** - Initializes DeepFilterNet
11. **Warmup** - Preheats all services (reduces first-request latency)

### Shutdown Order

Reverse of startup: TTS → Denoise → State Machine → Notification → Action → Intent → Ollama → Whisper → VAD

---

## 📄 License

This project is open-source. See the license file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📞 Support

For issues, questions, or suggestions, please open an issue on the repository.
