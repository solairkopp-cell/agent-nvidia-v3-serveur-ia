"""
Test du DenoiseProcessor - compare audio brut vs traité
"""
import sys
from pathlib import Path
import numpy as np

# Ajouter le dossier parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from experimental.denoise_processor import DenoiseProcessor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_denoise(input_file: str):
    """Tester le denoise sur un fichier"""
    
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ File not found: {input_file}")
        return
    
    output_path = input_path.with_name(f"{input_path.stem}_denoised.wav")
    
    processor = DenoiseProcessor()
    
    if not processor.startup():
        print("❌ Failed to initialize DeepFilterNet")
        return
    
    try:
        print(f"\n📂 Input: {input_path}")
        print(f"📂 Output: {output_path}")
        
        success = processor.process_file(str(input_path), str(output_path))
        
        if success and output_path.exists():
            # Compare file sizes
            input_size = input_path.stat().st_size
            output_size = output_path.stat().st_size
            
            print(f"\n✅ Success!")
            print(f"   Input size:  {input_size:,} bytes")
            print(f"   Output size: {output_size:,} bytes")
            print(f"   Ratio: {output_size/input_size*100:.1f}%")
            
            # Load and compare audio content
            import wave
            
            # Input
            with wave.open(str(input_path), 'rb') as wf:
                input_sr = wf.getframerate()
                input_samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            
            # Output
            with wave.open(str(output_path), 'rb') as wf:
                output_sr = wf.getframerate()
                output_samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            
            print(f"\n📊 Audio comparison:")
            print(f"   Input:  {len(input_samples):,} samples @ {input_sr}Hz ({len(input_samples)/input_sr:.2f}s)")
            print(f"   Output: {len(output_samples):,} samples @ {output_sr}Hz ({len(output_samples)/output_sr:.2f}s)")
            
            # RMS levels
            input_rms = np.sqrt(np.mean(input_samples.astype(np.float32)**2))
            output_rms = np.sqrt(np.mean(output_samples.astype(np.float32)**2))
            
            print(f"\n🔊 RMS levels:")
            print(f"   Input:  {input_rms:.1f} ({20*np.log10(input_rms/32768+1e-10):.1f} dB)")
            print(f"   Output: {output_rms:.1f} ({20*np.log10(output_rms/32768+1e-10):.1f} dB)")
            
            # Check if they're actually different
            if len(input_samples) == len(output_samples):
                diff = np.abs(input_samples.astype(np.float32) - output_samples.astype(np.float32))
                print(f"\n📈 Difference:")
                print(f"   Mean diff: {diff.mean():.1f}")
                print(f"   Max diff:  {diff.max():.1f}")
                print(f"   Identical: {np.array_equal(input_samples, output_samples)}")
                
                if np.array_equal(input_samples, output_samples):
                    print("\n⚠️  WARNING: Input and output are IDENTICAL! Denoising did nothing!")
                else:
                    print("\n✅ Audio was modified by DeepFilterNet")
            else:
                print(f"\n⚠️  Different lengths - cannot compare directly")
            
            print(f"\n🎧 Listen to both files:")
            print(f"   Raw:     {input_path}")
            print(f"   Denoised: {output_path}")
            
        else:
            print(f"❌ Processing failed")
            
    finally:
        processor.shutdown()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_denoise.py <input.wav>")
        print("Example: python test_denoise.py assets/recordings/recording_xxx_raw.wav")
        sys.exit(1)
    
    test_denoise(sys.argv[1])
