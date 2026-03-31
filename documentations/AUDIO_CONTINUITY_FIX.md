# Audio Continuity Fix - WebRTC TTS

## Problem

The audio was choppy/not continuous when sending TTS audio to WebRTC clients.

## Root Causes Identified

1. **Blocking `recv()`**: The original `TTSAudioTrack.recv()` blocked indefinitely on `queue.get()` when no TTS data was available, causing WebRTC to wait and create gaps.

2. **No silence frames**: When there was no TTS audio being generated, no frames were sent at all, breaking the continuous audio stream.

3. **Incorrect PTS timing**: Frames need monotonically increasing Presentation Timestamps (PTS) for smooth playback.

4. **Sleep in sender**: The `asyncio.sleep(0.02)` in the sender code was blocking and not synchronized with WebRTC's actual frame consumption rate.

## Solution

### 1. `TTSAudioTrack.recv()` with Timeout

```python
async def recv(self):
    try:
        # Wait for TTS frame with short timeout (10ms)
        frame = await asyncio.wait_for(self._queue.get(), timeout=self._frame_duration / 2)
    except asyncio.TimeoutError:
        # No TTS data → generate silence frame with correct PTS
        frame = self._create_silence_frame(pts=self._pts)
```

### 2. Generate Silence Frames

When no TTS audio is available, generate 20ms silence frames to keep the stream continuous:

```python
def _create_silence_frame(self, pts: int = 0) -> "av.AudioFrame":
    samples = np.zeros(self._samples_per_frame, dtype=np.int16)
    frame = av.AudioFrame.from_ndarray(
        samples.reshape(1, -1),  # mono
        format="s16",
        layout="mono",
    )
    frame.sample_rate = self._sample_rate
    frame.pts = pts  # Correct PTS
    frame.time_base = Fraction(1, self._sample_rate)
    return frame
```

### 3. Remove Sleep from Sender

**Before** (`agent_service.py`):
```python
for frame in frames:
    await session.tts_track.feed(frame)
    await asyncio.sleep(0.02)  # ❌ Blocks sender
```

**After**:
```python
for frame in frames:
    await session.tts_track.feed(frame)  # ✅ Queue immediately
# recv() handles timing (20ms per frame)
```

### 4. Correct PTS Tracking

Each frame (TTS or silence) advances the PTS counter:

```python
samples = getattr(frame, "samples", None)
if isinstance(samples, int) and samples > 0:
    self._pts += samples
else:
    self._pts += self._samples_per_frame
```

## Technical Details

### Frame Format
- **Sample rate**: 22,050 Hz (Piper native, no resampling needed)
- **Frame duration**: 20ms (standard for Opus codec)
- **Samples per frame**: 441 samples @ 22.05kHz
- **Format**: s16 (16-bit signed integer)
- **Layout**: mono

### Timing
- WebRTC calls `recv()` ~50 times per second (every 20ms)
- Timeout is set to 10ms (half frame duration) for responsiveness
- Silence frames are generated on-the-fly with correct PTS

## Files Modified

1. **`services/webrtc_service.py`**
   - `TTSAudioTrack.__init__()`: Added `_frame_duration` and `_stopped` flag
   - `TTSAudioTrack.recv()`: Added timeout + silence frame generation
   - `TTSAudioTrack._create_silence_frame()`: New method to create silence frames
   - `TTSAudioTrack.stop()`: New method to properly stop the track

2. **`services/agent_service.py`**
   - Removed `asyncio.sleep(0.02)` from all TTS feed loops (3 locations)
   - Added comments explaining that `recv()` handles timing

## Testing

1. Start the server:
   ```bash
   python main.py
   ```

2. Connect a WebRTC client

3. Speak to the agent and listen for:
   - ✅ No gaps between words
   - ✅ No clicking/popping sounds
   - ✅ Smooth audio playback
   - ✅ No robotic/choppy artifacts

4. Check logs for:
   ```
   INFO: TTS audio client_id=xxx phrase_len=YY samples=ZZZ frames=NN
   ```

## References

- [aiortc issue #1357](https://github.com/aiortc/aiortc/issues/1357) - Custom MediaStreamTrack audio quality
- [aiortc issue #1356](https://github.com/aiortc/aiortc/issues/1356) - Audio output delay
- [aiortc issue #571](https://github.com/aiortc/aiortc/issues/571) - Created audio tracks never call recv()
- [WebRTC audio streaming best practices](https://stackoverflow.com/questions/79105261/real-time-audio-streaming-issue-in-webrtc-using-python-aiortc)

## Notes

- The browser's WebRTC buffer handles smooth playback
- Silence frames keep the RTP stream active even when no TTS is speaking
- PTS must be monotonically increasing for proper audio synchronization
- 20ms frames are the WebRTC standard for Opus audio codec
