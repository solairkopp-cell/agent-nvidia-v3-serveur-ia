"""
experimental/denoise_processor.py
Service autonome pour débruiter des fichiers audio avec DeepFilterNet.

Usage:
    python -m experimental.denoise_processor input.wav output.wav
    ou
    from experimental.denoise_processor import DenoiseProcessor

    processor = DenoiseProcessor()
    processor.startup()
    processor.process_file("input.wav", "output.wav")
    processor.shutdown()
"""
import gc
import logging
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import torch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sur Jetson, GPU = CUDA:0 mais la mémoire est unifiée avec le CPU.
# DeepFilterNet est léger (~1M params), le gain GPU est marginal mais
# on l'active quand même pour libérer le CPU pour le reste du pipeline.
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class DenoiseProcessor:
    """
    Processeur de débruitage audio autonome utilisant DeepFilterNet.
    Utilise load_audio/save_audio natifs de df.enhance pour éviter
    tout resample manuel.
    """

    def __init__(self, model_name: str = "DeepFilterNet2"):
        self.model_name = model_name
        self._model = None
        self._df_state = None
        self._ready = False

    def startup(self) -> bool:
        """
        Initialiser DeepFilterNet et envoyer le modèle sur GPU si dispo.

        Returns:
            bool: True si initialisation réussie, False sinon
        """
        try:
            from df.enhance import init_df

            logger.info(f"Loading DeepFilterNet model: {self.model_name} on {DEVICE}")
            self._model, self._df_state, _ = init_df(default_model=self.model_name)

            # Pousser le modèle sur GPU si disponible
            self._model = self._model.to(DEVICE)

            self._ready = True
            logger.info(f"DeepFilterNet ready on {DEVICE}")
            return True

        except ImportError as e:
            logger.error(f"DeepFilter not installed: {e}")
            logger.error("Install with: pip install deepfilternet")
            return False
        except Exception as e:
            logger.error(f"Failed to load DeepFilterNet: {e}")
            return False

    def shutdown(self) -> None:
        """Libérer les ressources."""
        self._model = None
        self._df_state = None
        self._ready = False

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        gc.collect()
        logger.info("DenoiseProcessor shutdown complete")

    def process_file(self, input_path: str, output_path: str) -> bool:
        """
        Débruiter un fichier audio et le sauvegarder.
        Le resample vers 48kHz est géré en interne par DeepFilterNet.

        Args:
            input_path: Chemin du fichier d'entrée (wav)
            output_path: Chemin du fichier de sortie (wav)

        Returns:
            bool: True si succès, False sinon
        """
        if not self._ready:
            logger.error("DenoiseProcessor not started. Call startup() first.")
            return False

        if not Path(input_path).exists():
            logger.error(f"Input file not found: {input_path}")
            return False

        try:
            from df.enhance import enhance, load_audio, save_audio

            # load_audio resamples automatiquement vers df_state.sr() (48kHz)
            audio, _ = load_audio(input_path, sr=self._df_state.sr())

            logger.info(f"Processing: {input_path} | sr={self._df_state.sr()}Hz | "
                        f"duration={audio.shape[-1]/self._df_state.sr():.2f}s")

            enhanced = self._run_enhance(audio)

            # Créer le dossier de sortie si nécessaire
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # save_audio gère la conversion float -> int16
            save_audio(output_path, enhanced, self._df_state.sr())

            logger.info(f"Saved: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return False

    def process_array(self, samples: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Débruiter un array numpy directement.

        Args:
            samples: Audio samples (float32, mono, shape [T] ou [1, T])
            sample_rate: Sample rate réel des samples en entrée

        Returns:
            np.ndarray: Samples débruités au même sample_rate d'entrée
        """
        if not self._ready:
            logger.warning("DenoiseProcessor not started, returning original audio")
            return samples

        from scipy.signal import resample_poly

        # Normaliser shape -> [1, T]
        if samples.ndim == 1:
            audio = samples[np.newaxis, :]
        else:
            audio = samples

        # Resampler vers 48kHz si nécessaire
        df_sr = self._df_state.sr()  # 48000
        if sample_rate != df_sr:
            audio = resample_poly(audio, df_sr, sample_rate, axis=-1).astype(np.float32)

        tensor = torch.from_numpy(audio)
        enhanced = self._run_enhance(tensor)
        enhanced_np = enhanced.numpy()

        # Resampler vers le SR d'origine
        if sample_rate != df_sr:
            enhanced_np = resample_poly(enhanced_np, sample_rate, df_sr, axis=-1).astype(np.float32)

        return np.clip(enhanced_np.squeeze(0), -1.0, 1.0)

    def _run_enhance(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Lancer enhance() avec le tensor sur le bon device.

        Args:
            audio: Tensor [1, T] float32

        Returns:
            Tensor [1, T] float32 sur CPU
        """
        from df.enhance import enhance

        audio_dev = audio.to(DEVICE)

        with torch.inference_mode():
            enhanced = enhance(self._model, self._df_state, audio_dev)

        # Toujours ramener sur CPU avant de sortir
        return enhanced.cpu()


def main():
    """CLI pour débruiter des fichiers audio"""
    if len(sys.argv) < 3:
        print("Usage: python -m experimental.denoise_processor <input.wav> <output.wav>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    processor = DenoiseProcessor()

    if not processor.startup():
        print("Failed to initialize DeepFilterNet")
        sys.exit(1)

    try:
        success = processor.process_file(input_path, output_path)
        if success:
            print(f"✓ Denoised audio saved to: {output_path}")
        else:
            print("✗ Failed to process audio")
            sys.exit(1)
    finally:
        processor.shutdown()


if __name__ == "__main__":
    main()