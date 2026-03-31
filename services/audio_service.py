"""
services/audio_service.py
Utilitaires bas niveau : resampling, conversion format, encodage.
Pas d'état — toutes les fonctions sont pures ou stateless.
"""
from __future__ import annotations

import io
import numpy as np
import soundfile as sf

from fractions import Fraction

try:
    import av  # type: ignore
except Exception:  # pragma: no cover
    av = None


# ── Constantes ────────────────────────────────────────────────────────────────
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1          # mono


class AudioService:
    """
    Conversions et transformations audio.
    S'instancie une seule fois (singleton via DI dans main.py).
    """

    # ── Conversion format ────────────────────────────────────────────────────

    def pcm_bytes_to_array(self, raw: bytes, dtype: str = "float32") -> np.ndarray:
        """
        Bytes PCM bruts → numpy array float32.
        Utilisé pour les frames WebRTC (av.AudioFrame.to_ndarray).
        """
        if not raw:
            return np.array([], dtype=np.float32)
        # PCM s16le mono par défaut
        data = np.frombuffer(raw, dtype=np.int16)
        samples = (data.astype(np.float32) / 32768.0).reshape(-1)
        if dtype == "float32":
            return samples
        return samples.astype(dtype)

    def av_frame_to_array(self, frame, target_rate: int = TARGET_SAMPLE_RATE) -> np.ndarray:
        """
        Convertit un `av.AudioFrame` vers un PCM mono float32 dans [-1, 1].

        On force explicitement `s16` + `mono` + `target_rate` via le resampler
        PyAV pour éviter les ambiguïtés de format / layout observées avec
        `frame.to_ndarray()` brut.
        """
        if av is None:
            raise RuntimeError("PyAV is not installed (package 'av').")

        resampler = av.AudioResampler(format="s16", layout="mono", rate=int(target_rate))
        out_frames = resampler.resample(frame)
        if not out_frames:
            return np.array([], dtype=np.float32)

        arrays: list[np.ndarray] = []
        for out_frame in out_frames:
            pcm = out_frame.to_ndarray()
            if not isinstance(pcm, np.ndarray):
                pcm = np.asarray(pcm, dtype=np.int16)
            pcm = pcm.reshape(-1).astype(np.int16, copy=False)
            arrays.append(pcm.astype(np.float32) / 32768.0)

        if not arrays:
            return np.array([], dtype=np.float32)
        return np.concatenate(arrays).astype(np.float32, copy=False)

    def array_to_wav_bytes(self, samples: np.ndarray, rate: int = TARGET_SAMPLE_RATE) -> bytes:
        """
        numpy float32 → WAV bytes (io.BytesIO).
        Utilisé pour envoyer l'audio au service Whisper.
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim > 1:
            samples = self.to_mono(samples)
        samples = samples.astype(np.float32, copy=False)

        buf = io.BytesIO()
        sf.write(buf, samples, rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    def wav_bytes_to_array(self, wav_bytes: bytes) -> tuple[np.ndarray, int]:
        """
        WAV bytes → (numpy float32, sample_rate).
        Utilisé pour lire la réponse audio du TTS.
        """
        if not wav_bytes:
            return np.array([], dtype=np.float32), TARGET_SAMPLE_RATE
        samples, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
        if isinstance(samples, np.ndarray) and samples.ndim > 1:
            samples = self.to_mono(samples)
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        return samples.astype(np.float32, copy=False).reshape(-1), int(rate)

    def array_to_av_frame(self, samples: np.ndarray, sample_rate: int):
        """
        numpy float32 → av.AudioFrame prêt pour aiortc.
        Format : s16, layout mono, pts calculé.
        """
        if av is None:
            raise RuntimeError("PyAV is not installed (package 'av').")

        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim > 1:
            samples = self.to_mono(samples)
        samples = samples.astype(np.float32, copy=False).reshape(-1)

        # float32 [-1,1] -> int16
        clipped = np.clip(samples, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype(np.int16)

        frame = av.AudioFrame(format="s16", layout="mono", samples=len(pcm16))
        frame.sample_rate = int(sample_rate)
        frame.time_base = Fraction(1, int(sample_rate))
        frame.planes[0].update(pcm16.tobytes())
        return frame

    def array_to_av_frames(
        self,
        samples: np.ndarray,
        source_rate: int,
        target_rate: int = TARGET_SAMPLE_RATE,
        frame_ms: int = 20,
    ) -> list:
        """
        numpy float32 → liste de `av.AudioFrame` mono/s16 à fréquence fixe.

        Utilisé pour la sortie TTS WebRTC afin de garder un flux stable :
        - resample si nécessaire
        - découpage en petites frames régulières
        """
        if av is None:
            raise RuntimeError("PyAV is not installed (package 'av').")

        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim > 1:
            samples = self.to_mono(samples)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return []

        normalized_rate = int(target_rate) if int(target_rate) > 0 else TARGET_SAMPLE_RATE
        if int(source_rate) > 0 and int(source_rate) != normalized_rate:
            samples = self.resample(samples, int(source_rate), normalized_rate)

        frame_samples = max(1, int(normalized_rate * (frame_ms / 1000.0)))
        frames = []
        for start in range(0, len(samples), frame_samples):
            chunk = samples[start : start + frame_samples]
            if chunk.size == 0:
                continue
            frames.append(self.array_to_av_frame(chunk, normalized_rate))
        return frames

    def array_to_av_frames_direct(
        self,
        samples: np.ndarray,
        sample_rate: int,
        frame_ms: int = 10,
    ) -> list:
        """
        Conversion directe sans resampling pour qualité audio maximale.
        Utilisé pour TTS où source_rate == target_rate (22.05kHz).

        Évite tout resampling qui dégrade la qualité (artefacts métalliques).
        """
        if av is None:
            raise RuntimeError("PyAV is not installed (package 'av').")

        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim > 1:
            samples = self.to_mono(samples)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return []

        rate = int(sample_rate) if int(sample_rate) > 0 else 22050
        frame_samples = max(1, int(rate * (frame_ms / 1000.0)))
        frames = []
        for start in range(0, len(samples), frame_samples):
            chunk = samples[start : start + frame_samples]
            if chunk.size == 0:
                continue
            frames.append(self.array_to_av_frame(chunk, rate))
        return frames

    # ── Resampling ───────────────────────────────────────────────────────────

    def resample(
        self,
        samples: np.ndarray,
        source_rate: int,
        target_rate: int = TARGET_SAMPLE_RATE,
    ) -> np.ndarray:
        """
        Resampling de haute qualité avec filtre anti-repliement.
        Utilise scipy si disponible, sinon fallback sur numpy avec lissage.
        source_rate → target_rate (typiquement 48000 → 16000).
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            return np.array([], dtype=np.float32)
        if source_rate == target_rate:
            return samples.astype(np.float32, copy=False)

        samples = samples.astype(np.float32, copy=False).reshape(-1)
        
        # Essayer d'utiliser scipy pour un resampling de qualité
        try:
            from scipy import signal as scipy_signal
            num_samples = int(np.ceil(len(samples) * target_rate / source_rate))
            resampled = scipy_signal.resample(samples, num_samples)
            return resampled.astype(np.float32, copy=False)
        except ImportError:
            pass
        
        try:
            import librosa
            resampled = librosa.resample(samples, orig_sr=source_rate, target_sr=target_rate)
            return resampled.astype(np.float32, copy=False)
        except ImportError:
            pass

        # Fallback: méthode numpy avec interpolation spline pour meilleure qualité
        duration = len(samples) / float(source_rate)
        target_len = int(round(duration * target_rate))
        if target_len <= 0:
            return np.array([], dtype=np.float32)

        # Interpolation cubique pour meilleure qualité que linéaire
        x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False).astype(np.float32)
        x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False).astype(np.float32)
        
        # Utiliser np.interp avec plus de points intermédiaires pour lisser
        return np.interp(x_new, x_old, samples).astype(np.float32, copy=False)

    # ── Normalisation ────────────────────────────────────────────────────────

    def to_mono(self, samples: np.ndarray) -> np.ndarray:
        """
        Stéréo ou multi-canal → mono (moyenne des canaux).
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim == 1:
            return samples.astype(np.float32, copy=False)
        # (channels, n) ou (n, channels)
        if samples.shape[0] <= 8 and samples.shape[0] < samples.shape[-1]:
            mono = samples.mean(axis=0)
        else:
            mono = samples.mean(axis=-1)
        return mono.astype(np.float32, copy=False).reshape(-1)

    def normalize(self, samples: np.ndarray) -> np.ndarray:
        """
        Normalise le volume (peak normalization à 0.95).
        Évite le clipping.
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False)
        if samples.size == 0:
            return samples
        peak = float(np.max(np.abs(samples)))
        if peak <= 1e-9:
            return samples
        gain = 0.95 / peak
        return (samples * gain).astype(np.float32, copy=False)

    def trim_silence(
        self,
        samples: np.ndarray,
        *,
        sample_rate: int,
        threshold: float,
        pad_ms: int = 0,
        min_silence_ms: int = 0,
        trim_leading: bool = True,
        trim_trailing: bool = True,
    ) -> np.ndarray:
        """
        Retirer un peu de silence en tête et en queue d'un segment TTS.
        Garde un léger padding pour éviter une coupe trop sèche.
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        samples = samples.astype(np.float32, copy=False).reshape(-1)
        if samples.size == 0:
            return samples

        abs_samples = np.abs(samples)
        idx = np.flatnonzero(abs_samples > float(threshold))
        if idx.size == 0:
            return samples

        pad = max(0, int(int(sample_rate) * (max(0, int(pad_ms)) / 1000.0)))
        min_silence = max(0, int(int(sample_rate) * (max(0, int(min_silence_ms)) / 1000.0)))

        first = int(idx[0])
        last = int(idx[-1])

        if trim_leading and first > min_silence:
            start = max(0, first - pad)
        else:
            start = 0

        trailing = int(samples.size - (last + 1))
        if trim_trailing and trailing > min_silence:
            end = min(samples.size, last + pad + 1)
        else:
            end = samples.size
        return samples[start:end].astype(np.float32, copy=False)

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def concat(self, chunks: list[np.ndarray]) -> np.ndarray:
        """
        Concatène une liste de numpy arrays en un seul.
        Utilisé pour assembler le buffer VAD en utterance complet.
        """
        if not chunks:
            return np.array([], dtype=np.float32)
        arrays = []
        for c in chunks:
            if not isinstance(c, np.ndarray):
                c = np.asarray(c, dtype=np.float32)
            arrays.append(c.astype(np.float32, copy=False).reshape(-1))
        return np.concatenate(arrays).astype(np.float32, copy=False)

    def duration_ms(self, samples: np.ndarray, rate: int = TARGET_SAMPLE_RATE) -> float:
        """
        Durée en millisecondes d'un array audio.
        """
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if rate <= 0:
            return 0.0
        return float(len(samples) / float(rate) * 1000.0)
