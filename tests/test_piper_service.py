import asyncio
import numpy as np
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from services.piper_tts_service import PiperTTSService
import config

async def test_piper_synthesis():
    print("Initializing PiperTTSService...")
    service = PiperTTSService()
    
    # Check if model files exist
    if not Path(config.PIPER_MODEL_PATH).exists():
        print(f"Error: Model not found at {config.PIPER_MODEL_PATH}")
        return
    
    await service.startup()
    
    print("Testing full synthesis...")
    text = "Hello, this is a test of the Danny Low voice using Piper TTS."
    samples, rate = await service.synthesize(text)
    
    print(f"Synthesis successful: {len(samples)} samples at {rate}Hz")
    assert isinstance(samples, np.ndarray)
    assert len(samples) > 0
    assert rate > 0
    
    print("Testing streaming synthesis...")
    async def token_gen():
        tokens = ["This ", "is ", "a ", "streaming ", "test."]
        for t in tokens:
            yield t
            await asyncio.sleep(0.1)
    
    count = 0
    async for phrase, s, r in service.synthesize_stream(token_gen()):
        print(f"Received segment: '{phrase}' ({len(s)} samples)")
        count += 1
    
    assert count > 0
    print("Streaming synthesis successful.")
    
    print("Health check...")
    is_healthy = await service.health_check()
    print(f"Health check: {is_healthy}")
    assert is_healthy
    
    await service.shutdown()
    print("PiperTTSService test passed!")

if __name__ == "__main__":
    asyncio.run(test_piper_synthesis())
