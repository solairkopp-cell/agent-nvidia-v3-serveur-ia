# MediaPlayer Integration Guide

## Overview

The aiortc `MediaPlayer` has been integrated into the WebRTC service to allow streaming audio from various sources (files, HTTP streams, webcam, microphone) directly into WebRTC connections.

## Configuration

Add these environment variables to enable MediaPlayer:

### Basic Configuration

```bash
# Enable MediaPlayer (default: false)
MEDIA_PLAYER_ENABLED=true

# Source path/URL (file, HTTP stream, or device)
MEDIA_PLAYER_SOURCE="/path/to/audio.mp3"

# Loop playback (default: false)
MEDIA_PLAYER_LOOP=true
```

### Advanced Configuration

```bash
# Format hint (optional, auto-detected if not specified)
# Examples: "v4l2" (Linux webcam), "avfoundation" (macOS), "dshow" (Windows)
MEDIA_PLAYER_FORMAT=""

# FFmpeg options as JSON string (optional)
MEDIA_PLAYER_OPTIONS='{"video_size":"640x480"}'
```

## Usage Examples

### 1. Play an Audio File

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE="/path/to/music.mp3"
export MEDIA_PLAYER_LOOP=true
python main.py
```

### 2. Stream from HTTP URL

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE="http://download.tsi.telecom-paristech.fr/gpac/dataset/dash/uhd/mux_sources/hevcds_720p30_2M.mp4"
python main.py
```

### 3. Use Webcam (Linux)

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE="/dev/video0"
export MEDIA_PLAYER_FORMAT="v4l2"
export MEDIA_PLAYER_OPTIONS='{"video_size":"640x480"}'
python main.py
```

### 4. Use Webcam (macOS)

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE="default:none"
export MEDIA_PLAYER_FORMAT="avfoundation"
export MEDIA_PLAYER_OPTIONS='{"video_size":"640x480"}'
python main.py
```

### 5. Use Webcam (Windows)

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE="video=Integrated Camera"
export MEDIA_PLAYER_FORMAT="dshow"
export MEDIA_PLAYER_OPTIONS='{"video_size":"640x480"}'
python main.py
```

### 6. Use Default Microphone

```bash
export MEDIA_PLAYER_ENABLED=true
export MEDIA_PLAYER_SOURCE=""  # Empty = default system microphone
python main.py
```

## Architecture

### New Components

1. **`MediaPlayerAudioTrack`** (`services/webrtc_service.py`)
   - Wrapper around `aiortc.MediaPlayer`
   - Relays audio frames from MediaPlayer to WebRTC
   - Implements `MediaStreamTrack` interface

2. **Configuration** (`config.py`)
   - `MEDIA_PLAYER_SOURCE`: Path or URL to media source
   - `MEDIA_PLAYER_FORMAT`: Format hint (v4l2, avfoundation, dshow)
   - `MEDIA_PLAYER_OPTIONS`: FFmpeg options as JSON
   - `MEDIA_PLAYER_LOOP`: Whether to loop playback
   - `MEDIA_PLAYER_ENABLED`: Enable/disable feature

3. **WebRTCService Updates**
   - Added `player` parameter to constructor
   - `create_peer()`: Adds MediaPlayer track if configured
   - `cleanup()`: Properly stops MediaPlayer on disconnect

4. **Main.py Updates**
   - Creates MediaPlayer instance if enabled
   - Injects into WebRTCService
   - Handles shutdown cleanup

## How It Works

```
┌─────────────────┐
│ MediaPlayer     │ (file/URL/device)
│ aiortc.contrib  │
└────────┬────────┘
         │
         │ audio frames
         ▼
┌─────────────────┐
│ MediaPlayer     │
│ AudioTrack      │
└────────┬────────┘
         │
         │ WebRTC stream
         ▼
┌─────────────────┐
│ RTCPeerConnection │
└────────┬────────┘
         │
         │ SDP negotiation
         ▼
┌─────────────────┐
│ Client Browser  │
│ (receives audio)│
└─────────────────┘
```

## API Reference

### MediaPlayerAudioTrack

```python
class MediaPlayerAudioTrack(MediaStreamTrack):
    """Wrapper around aiortc.MediaPlayer for continuous audio streaming."""
    
    kind = "audio"
    
    def __init__(self, player: MediaPlayer):
        """Initialize with a MediaPlayer instance."""
        
    async def recv(self):
        """Get next audio frame from MediaPlayer."""
        
    def stop(self):
        """Stop playback."""
```

### WebRTCService

```python
class WebRTCService:
    def __init__(
        self,
        vad: VADService,
        agent: AgentService,
        audio: AudioService,
        player: Optional[MediaPlayer] = None,  # New parameter
    ):
```

## Testing

1. **Start the server:**
   ```bash
   export MEDIA_PLAYER_ENABLED=true
   export MEDIA_PLAYER_SOURCE="/path/to/test.mp3"
   python main.py
   ```

2. **Connect a WebRTC client** to the server

3. **Verify audio playback** in the browser/client

4. **Check logs:**
   ```
   INFO: MediaPlayer created: source=/path/to/test.mp3, format=auto, loop=true
   INFO: MediaPlayer audio track added to peer client_id=xxx
   INFO: MediaPlayerAudioTrack started
   ```

## Troubleshooting

### MediaPlayer not created
- Check `MEDIA_PLAYER_ENABLED=true`
- Verify `aiortc` and `av` (PyAV) are installed
- Check file path exists and is readable

### No audio playback
- Verify MediaPlayer has audio track: `player.audio is not None`
- Check codec compatibility (Opus, PCM, MP3, AAC supported)
- Enable debug logging

### FFmpeg errors
- Install FFmpeg: `sudo apt-get install ffmpeg` (Linux) or `brew install ffmpeg` (macOS)
- Check format/options are correct for source type

## Notes

- MediaPlayer runs continuously in the background
- When `MEDIA_PLAYER_LOOP=true`, the file replays indefinitely
- Multiple clients can connect to the same MediaPlayer stream
- MediaPlayer is stopped gracefully on server shutdown

## Migration from Previous Implementation

If you were using custom media handling:

1. Remove custom media track implementations
2. Set `MEDIA_PLAYER_ENABLED=true` in environment
3. Configure `MEDIA_PLAYER_SOURCE` with your media path
4. The WebRTC service will automatically add the MediaPlayer track

## See Also

- [aiortc Documentation](https://aiortc.readthedocs.io/)
- [PyAV Documentation](https://pyav.org/docs/)
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
