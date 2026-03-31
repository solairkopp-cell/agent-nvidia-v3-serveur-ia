# Kokoro-82M TTS Setup

## Migration from Piper to Kokoro

This server now uses **Kokoro-82M** (ONNX) instead of Piper for text-to-speech synthesis.

### Key Features
- **Model**: Kokoro-82M (82M parameters)
- **Format**: ONNX (CPU optimized, int8 quantized)
- **Voice**: `af_sarah` (American Female) - default
- **Language**: English (en-us)
- **Sample Rate**: 24kHz
- **Speed**: Configurable (default: 1.0)

## Installation

### 1. Install Dependencies

```bash
pip install kokoro-onnx soundfile
```

### 2. Download Model Files

Download the model and voices files from the official release:

```bash
cd /home/server/aiserver/assets/models/

# Download model (int8 quantized for CPU)
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx

# Download voices file
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

### 3. Configure Environment (Optional)

Edit `.env` or set environment variables:

```bash
# Model paths (default: assets/models/)
KOKORO_MODEL_PATH=assets/models/kokoro-v1.0.int8.onnx
KOKORO_VOICES_PATH=assets/models/voices-v1.0.bin

# Voice selection
KOKORO_VOICE=af_sarah  # American Female (Sarah)

# Other available voices:
# - af_bella (American Female)
# - am_adam (American Male)
# - am_michael (American Male)
# - bf_emma (British Female)
# - bm_daniel (British Male)
# etc.

# Language
KOKORO_LANGUAGE=en-us

# Speech speed (1.0 = normal, >1 = faster, <1 = slower)
KOKORO_SPEED=1.0
```

## Available Voices

### American Female
- `af_heart`, `af_alloy`, `af_aoede`, `af_bella`, `af_jessica`, `af_kore`, `af_nicole`, `af_nova`, `af_river`, **`af_sarah`**, `af_sky`

### American Male
- `am_adam`, `am_echo`, `am_eric`, `am_fenrir`, `am_liam`, `am_michael`, `am_onyx`, `am_puck`, `am_santa`

### British Female
- `bf_alice`, `bf_emma`, `bf_isabella`, `bf_lily`

### British Male
- `bm_daniel`, `bm_fable`, `bm_george`, `bm_lewis`

## Testing

After setup, test the TTS:

```bash
python -c "
from services.kokoro_tts_service import KokoroTTSService
import asyncio

async def test():
    tts = KokoroTTSService()
    await tts.startup()
    samples, rate = await tts.synthesize('Hello, this is Kokoro TTS with Sarah voice.')
    print(f'Generated {len(samples)} samples at {rate}Hz')
    await tts.shutdown()

asyncio.run(test())
"
```

## Performance

- **CPU Only**: Runs on CPU (no GPU required)
- **Lightweight**: 82M parameters, int8 quantized
- **Fast**: Optimized for real-time synthesis

## Configuration Reference

See `config.py`:
```python
KOKORO_MODEL_PATH = os.getenv("KOKORO_MODEL_PATH", "assets/models/kokoro-v1.0.int8.onnx")
KOKORO_VOICES_PATH = os.getenv("KOKORO_VOICES_PATH", "assets/models/voices-v1.0.bin")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_sarah")
KOKORO_LANGUAGE = os.getenv("KOKORO_LANGUAGE", "en-us")
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))
```

## Troubleshooting

### Model not found error
Ensure the model files are downloaded and placed in `assets/models/`:
- `kokoro-v1.0.int8.onnx`
- `voices-v1.0.bin`

### Import error: kokoro_onnx
Install the package:
```bash
pip install kokoro-onnx
```

### Audio quality issues
Try adjusting the speed:
```bash
export KOKORO_SPEED=0.9  # Slightly slower for better quality
```

## Migration Notes

### Files Changed
- `services/kokoro_tts_service.py` - New TTS service
- `config.py` - Added Kokoro configuration
- `main.py` - Switched from PiperTTSService to KokoroTTSService

### Files Unchanged
- `services/piper_tts_service.py` - Kept for reference (not used)

### API Compatibility
The Kokoro service has the same interface as Piper:
- `synthesize(text)` → `(samples, sample_rate)`
- `synthesize_stream(text_stream)` → AsyncIterator
- `health_check()` → bool

No changes needed in AgentService or other dependent services.
