#!/bin/bash
# scripts/download_kokoro_models.sh
# Download Kokoro-82M model and voices files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
MODELS_DIR="$PROJECT_ROOT/assets/models"

echo "🎵 Downloading Kokoro-82M TTS models..."
echo "Target directory: $MODELS_DIR"

# Create models directory if it doesn't exist
mkdir -p "$MODELS_DIR"

# Download model file
echo "⬇️  Downloading kokoro-v1.0.int8.onnx..."
wget -O "$MODELS_DIR/kokoro-v1.0.int8.onnx" \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx

# Download voices file
echo "⬇️  Downloading voices-v1.0.bin..."
wget -O "$MODELS_DIR/voices-v1.0.bin" \
  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

echo "✅ Models downloaded successfully!"
echo ""
echo "Files:"
ls -lh "$MODELS_DIR"/kokoro-* "$MODELS_DIR"/voices-*

echo ""
echo "To test the installation:"
echo "  cd $PROJECT_ROOT"
echo "  python -c \"from services.kokoro_tts_service import KokoroTTSService; import asyncio; asyncio.run(KokoroTTSService().startup())\""
