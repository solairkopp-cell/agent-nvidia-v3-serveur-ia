# Piper Streaming Server 🚀

A high-performance, low-latency Text-to-Speech (TTS) server built around the [Piper](https://github.com/rhasspy/piper) engine. This server is specifically designed and optimized for **Real-Time AI Agents (LLMs)**, offering sub-500ms *Time-To-First-Audio* (TTFA) and native support for LLM token-by-token streaming.

---

## 🎯 Role & Capabilities

Traditional TTS pipelines wait for an entire sentence to be generated before synthesizing audio, causing massive latency. This server solves this by introducing a highly optimized **streaming architecture**:

1. **LLM Token Streaming**: Feed words as soon as your LLM generates them. The server intelligently buffers tokens and flushes them to the audio engine the millisecond a punctuation mark is reached.
2. **First-Come, First-Served Interruption**: If the user interrupts the AI, the server instantly purges all queues and audio buffers (`tts_interrupt`), allowing the AI to reply immediately without restarting the heavy ONNX process.
3. **Zero Cold-Starts**: A background keep-alive loop ensures the ONNX engine never goes to sleep, preventing multi-second latency spikes on the first interaction.
4. **Binary Audio Broadcasting**: Audio is streamed directly as raw PCM Float32 binary chunks over WebSockets, ready to be scheduled gaplessly by the browser's Web Audio API.

---

## 🏗️ Architecture

The server operates asynchronously using `aiohttp` and `asyncio`, split into three main layers:

1. **WebSocket Layer (`main_engine.py`)**: 
   - Handles incoming WebSocket connections on port `9000`.
   - Maintains a thread-safe `AudioBus` to broadcast generated PCM audio chunks to all connected clients.
2. **Orchestrator Layer (`PiperEngineManager`)**:
   - Manages an internal `Queue` for phrases.
   - Splits incoming text or streamed tokens into optimal chunks using punctuation heuristics.
   - Handles the 3-second keep-alive pings (`.`) to prevent ONNX sleep.
3. **Subprocess Layer (`PiperTTSService`)**:
   - Wraps the C++ Piper binary in a persistent, non-blocking `asyncio.subprocess`.
   - Reads the raw `stdout` stream continuously without blocking the event loop.
   - Uses `soxr` to resample Piper's native 22050 Hz output to 48000 Hz in real-time.

---

## 📁 File Structure

```text
piper-streaming-server/
│
├── main_engine.py                  # Entry point: aiohttp server & WebSocket handler
├── config.py                       # Configuration (Model paths, binary path)
│
├── services/
│   ├── piper_engine_manager.py     # State machine, Text splitting, Token buffering, Keep-alive
│   └── piper_tts_service.py        # Async subprocess wrapper, SOXR audio resampling
│
├── dashboard/
│   ├── dashboard.py                # Simple HTTP server for the UI (Port 9001)
│   └── index.html                  # Web UI to visualize latency, VU meter, and stream testing
│
├── voices/                         # Directory containing ONNX models (e.g. en_US-lessac-medium)
│   ├── en_US-lessac-medium.onnx
│   └── en_US-lessac-medium.onnx.json
│
└── test_stream.py                  # Python test script simulating an LLM streaming tokens
```

---

## 🔌 API Reference (WebSockets)

Connect via WebSocket to: `ws://localhost:9000/`

### 📥 Inputs (JSON)

The server accepts 4 types of JSON messages:

**1. Legacy Block Mode**
Instantly interrupts any ongoing speech and speaks the provided text.
```json
{
  "type": "tts",
  "text": "The quick brown fox jumps over the lazy dog."
}
```

**2. Token Streaming (Recommended for LLMs)**
Append a newly generated LLM token to the buffer. If punctuation is found, the phrase is extracted and spoken instantly.
```json
{
  "type": "tts_stream",
  "text": " Hello"
}
```

**3. Stream Flush**
Used when the LLM finishes generation (e.g., emits `[DONE]`). Forces the server to speak any remaining words in the buffer that didn't have punctuation.
```json
{
  "type": "tts_stream_flush"
}
```

**4. Hard Interrupt**
Instantly clears all text buffers, audio queues, and stops current playback. Crucial for Voice Activity Detection (VAD) when the user cuts the AI off.
```json
{
  "type": "tts_interrupt"
}
```

### 📤 Outputs (Binary PCM)

The server does **not** return JSON. It streams raw binary audio frames directly over the WebSocket.

**Binary Frame Structure:**
- **Bytes 0-3:** `UInt32` (Little Endian) -> Number of Audio Samples (`N`)
- **Bytes 4-end:** `Float32Array` of size `N` -> PCM Audio data

**Audio Specs:**
- **Sample Rate:** 48000 Hz
- **Channels:** 1 (Mono)
- **Format:** 32-bit Float (`f32le`)

*These binary frames can be directly decoded and played using the browser's `AudioContext.createBufferSource()`.*

---

## 🤖 Integrating with Ollama (Python Example)

Connecting a local LLM like Ollama directly to the TTS stream is incredibly simple. By passing `stream=True` to Ollama, you can capture tokens as they are generated and forward them instantly to the TTS WebSocket.

```python
import asyncio
import json
import websockets
import ollama # pip install ollama

async def stream_ollama_to_tts(prompt: str):
    # Connect to the Piper TTS Streaming Server
    async with websockets.connect("ws://localhost:9000/") as ws:
        
        # 1. Instantly interrupt any ongoing TTS (useful if the human user just spoke)
        await ws.send(json.dumps({"type": "tts_interrupt"}))
        
        # 2. Start streaming generation from your local LLM
        print("LLM Thinking...")
        response = ollama.chat(
            model='qwen2.5:4b', 
            messages=[{'role': 'user', 'content': prompt}],
            stream=True
        )
        
        # 3. Stream tokens exactly as they arrive!
        for chunk in response:
            token = chunk['message']['content']
            if token:
                print(token, end='', flush=True)
                # Send the token to the TTS server
                await ws.send(json.dumps({
                    "type": "tts_stream", 
                    "text": token
                }))
                
        # 4. Flush the remaining text buffer when LLM is completely finished
        await ws.send(json.dumps({"type": "tts_stream_flush"}))
        print("\n[Stream Finished]")

# To run the test:
# asyncio.run(stream_ollama_to_tts("Tell me a short story in 3 sentences."))
```

---

## 🚀 Getting Started

1. **Start the Engine:**
   ```bash
   python main_engine.py
   ```
2. **Start the Dashboard (Optional, for testing):**
   ```bash
   cd dashboard && python dashboard.py
   ```
3. **Open the Dashboard:** Go to `http://localhost:9001/` to test latency and simulate LLM streaming visually.
