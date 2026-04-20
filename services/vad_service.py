"""
services/vad_service.py
Voice Activity Detection via Silero VAD (ONNX).

Responsabilité :
  - Charger le modèle Silero une seule fois au démarrage
  - Scorer chaque chunk audio (32ms)
  - Décider si on est en phase de parole ou de silence
  - Signaler la fin d'utterance quand le silence est suffisamment long

NB : le modèle ONNX est partagé entre toutes les sessions.
     L'état VAD (buffer, compteurs) est dans Session, pas ici.
"""
from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np

import config
from models.session import Session


@dataclass
class VADResult:
    """Résultat du traitement d'un chunk par le VAD."""
    type: str           # "speech_start" | "speech" | "silence" | "utterance_end"
    speech_prob: float  # score Silero brut (0.0 → 1.0)
    audio: Optional[np.ndarray] = None  # rempli uniquement si type == "utterance_end"
    ignored_short: bool = False         # True si utterance trop courte ignorée


class VADService:
    """
    Singleton. Chargé une fois dans main.py et injecté dans le service audio.
    """

    def __init__(self):
        self._model = None  # SileroVadOnnx (chargé dans startup())
        self._chunk_samples: int = 0   # calculé depuis config.VAD_CHUNK_MS
        self._silence_threshold: int = 0  # nb chunks silence → utterance_end
        self._min_speech_chunks: int = 0  # nb chunks min pour valider utterance
        self._start_trigger_chunks: int = 1  # nb chunks parole consécutifs avant speech_start
        self._pre_roll_chunks: int = 0    # nb chunks gardés avant speech_start
        self._post_roll_chunks: int = 0   # nb chunks gardés après fin détectée
        self._max_speech_chunks: int = 0  # garde-fou durée max utterance
        # États récurrents fallback (si score() est appelé sans session)
        self._h: Optional[np.ndarray] = None
        self._c: Optional[np.ndarray] = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger le modèle Silero ONNX depuis config.SILERO_MODEL_PATH.
        Calculer les seuils en chunks depuis les constantes ms.
        Appelé une fois au démarrage de l'application (lifespan FastAPI).
        """
        self._chunk_samples = int(config.SAMPLE_RATE * (config.VAD_CHUNK_MS / 1000.0))
        if self._chunk_samples <= 0:
            raise ValueError("Invalid VAD_CHUNK_MS / SAMPLE_RATE configuration.")

        # 480ms / 32ms -> 15 chunks (ceil pour être conservateur)
        self._silence_threshold = int(math.ceil(config.VAD_SILENCE_DURATION_MS / config.VAD_CHUNK_MS))
        # 300ms / 32ms -> 10 chunks (ceil)
        self._min_speech_chunks = int(math.ceil(config.VAD_MIN_SPEECH_MS / config.VAD_CHUNK_MS))
        self._start_trigger_chunks = max(1, int(getattr(config, "VAD_START_TRIGGER_CHUNKS", 1)))
        self._pre_roll_chunks = int(math.ceil(config.VAD_PRE_ROLL_MS / config.VAD_CHUNK_MS)) if config.VAD_PRE_ROLL_MS > 0 else 0
        self._post_roll_chunks = int(math.ceil(config.VAD_POST_ROLL_MS / config.VAD_CHUNK_MS)) if config.VAD_POST_ROLL_MS > 0 else 0
        # 6000ms / 32ms -> 188 chunks (ceil). 0 ou négatif -> désactivé.
        if getattr(config, "VAD_MAX_UTTERANCE_MS", 0) and config.VAD_MAX_UTTERANCE_MS > 0:
            self._max_speech_chunks = int(math.ceil(config.VAD_MAX_UTTERANCE_MS / config.VAD_CHUNK_MS))
        else:
            self._max_speech_chunks = 0

        def _load_session():
            try:
                import onnxruntime as ort  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise RuntimeError(
                    "Dependency 'onnxruntime' is required for VADService. "
                    "Install requirements.txt."
                ) from exc

            if not os.path.exists(config.SILERO_MODEL_PATH):
                raise FileNotFoundError(
                    f"Silero VAD ONNX model not found at '{config.SILERO_MODEL_PATH}'. "
                    "Set env var SILERO_MODEL_PATH to the correct .onnx file path, "
                    "or place the model at the default location (assets/models/silero_vad.onnx)."
                )

            providers = ["CPUExecutionProvider"]
            available = ort.get_available_providers()
            # Sur Orin Nano 8GB, CUDA est préférable à TensorRT pour éviter les pics de RAM au démarrage
            if "CUDAExecutionProvider" in available:
                providers.insert(0, "CUDAExecutionProvider")
            if "TensorrtExecutionProvider" in available:
                providers.append("TensorrtExecutionProvider")

            return ort.InferenceSession(
                config.SILERO_MODEL_PATH,
                providers=providers,
            )

        # Charger en thread pour ne pas bloquer l'event loop.
        self._model = await asyncio.to_thread(_load_session)

    async def shutdown(self):
        """Libérer les ressources ONNX."""
        self._model = None

    # ── Traitement par session ────────────────────────────────────────────────

    def process_chunk(self, session: Session, chunk: np.ndarray) -> VADResult:
        """
        Traite un chunk de config.VAD_CHUNK_MS ms pour une session donnée.

        Lit et met à jour l'état VAD dans session :
          session.is_speaking
          session.silence_chunks
          session.speech_chunks
          session.audio_buffer

        Retourne un VADResult :
          - "speech_start"   : début de parole détecté
          - "speech"         : parole en cours
          - "silence"        : silence (pas encore assez long)
          - "utterance_end"  : fin d'utterance → audio contient le buffer complet

        Règles :
          speech_prob > config.VAD_SILENCE_THRESHOLD → speech
          silence_chunks >= _silence_threshold ET speech_chunks >= _min_speech_chunks → utterance_end
          utterance trop courte → réinitialiser le buffer sans déclencher STT
        """
        chunk = self.pad_chunk(chunk)
        speech_prob = float(self.score(chunk, session=session))
        # Hysteresis : seuil différent pour continuer la parole vs démarrer.
        if session.is_speaking:
            threshold = float(getattr(config, "VAD_CONTINUE_THRESHOLD", config.VAD_SILENCE_THRESHOLD))
        else:
            threshold = float(config.VAD_SILENCE_THRESHOLD)
        is_speech = speech_prob > threshold

        if is_speech:
            if not session.is_speaking:
                session.speech_start_buffer.append(chunk.copy())
                if len(session.speech_start_buffer) < self._start_trigger_chunks:
                    return VADResult(type="silence", speech_prob=speech_prob)

                session.is_speaking = True
                if session.pre_speech_buffer:
                    session.audio_buffer.extend(session.pre_speech_buffer)
                    session.pre_speech_buffer.clear()
                session.audio_buffer.extend(session.speech_start_buffer)
                session.speech_start_buffer.clear()
                session.silence_chunks = 0
                session.post_roll_chunks = 0
                session.speech_chunks = self._start_trigger_chunks
                return VADResult(type="speech_start", speech_prob=speech_prob)

            session.audio_buffer.append(chunk)
            session.silence_chunks = 0
            session.post_roll_chunks = 0
            session.speech_chunks += 1

            # Garde-fou : utterance trop longue (bruit/écho), forcer un end.
            if self._max_speech_chunks and session.speech_chunks >= self._max_speech_chunks:
                audio = np.concatenate(session.audio_buffer) if session.audio_buffer else np.array([], dtype=np.float32)
                session.reset_audio_buffer()
                return VADResult(type="utterance_end", speech_prob=speech_prob, audio=audio)

            return VADResult(type="speech", speech_prob=speech_prob)

        # Silence
        if not session.is_speaking:
            self._flush_speech_start_buffer(session)
            self._remember_pre_roll(session, chunk)
            return VADResult(type="silence", speech_prob=speech_prob)

        session.silence_chunks += 1
        session.audio_buffer.append(chunk)
        if session.silence_chunks > self._silence_threshold:
            session.post_roll_chunks = session.silence_chunks - self._silence_threshold
        else:
            session.post_roll_chunks = 0

        if session.silence_chunks >= self._silence_threshold + self._post_roll_chunks:
            # Fin d'utterance candidate
            if session.speech_chunks >= self._min_speech_chunks:
                audio = np.concatenate(session.audio_buffer) if session.audio_buffer else np.array([], dtype=np.float32)
                session.reset_audio_buffer()
                return VADResult(type="utterance_end", speech_prob=speech_prob, audio=audio)

            # Utterance trop courte → ignorer
            session.reset_audio_buffer()
            return VADResult(type="silence", speech_prob=speech_prob, ignored_short=True)

        return VADResult(type="silence", speech_prob=speech_prob)

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def score(self, chunk: np.ndarray, session: Optional[Session] = None) -> float:
        """
        Appel direct au modèle Silero.
        Retourne la probabilité de présence vocale (0.0 → 1.0).
        Le chunk doit faire exactement self._chunk_samples samples @ 16kHz.
        """
        if self._model is None:
            raise RuntimeError("VADService not started (startup() not called).")

        chunk = self.pad_chunk(chunk)
        model = self._model

        # Tests: _model est un MagicMock callable.
        if callable(model):
            out = model(chunk)
            return _as_float(out)

        # Runtime: onnxruntime.InferenceSession
        run = getattr(model, "run", None)
        get_inputs = getattr(model, "get_inputs", None)
        if callable(run) and callable(get_inputs):
            inputs = model.get_inputs()
            if len(inputs) < 1:
                raise RuntimeError("Invalid ONNX model: no inputs.")
            input_names = [i.name for i in inputs]
            x_name = input_names[0]

            inp_x = chunk.astype(np.float32, copy=False)[None, :]

            # Silero VAD ONNX courant attend x + h + c (RNN states)
            need_state = len(input_names) >= 3
            if need_state:
                h_name = input_names[1]
                c_name = input_names[2]

                # Stocker l'état par session si fourni, sinon fallback global.
                if session is not None:
                    h = getattr(session, "vad_h", None)
                    c = getattr(session, "vad_c", None)
                else:
                    h = self._h
                    c = self._c

                if not isinstance(h, np.ndarray):
                    h = np.zeros((2, 1, 64), dtype=np.float32)
                if not isinstance(c, np.ndarray):
                    c = np.zeros((2, 1, 64), dtype=np.float32)

                outputs = model.run(None, {x_name: inp_x, h_name: h, c_name: c})
                # outputs: prob, new_h, new_c
                if len(outputs) >= 3:
                    new_h, new_c = outputs[1], outputs[2]
                    if session is not None:
                        setattr(session, "vad_h", new_h)
                        setattr(session, "vad_c", new_c)
                    else:
                        self._h, self._c = new_h, new_c
            else:
                outputs = model.run(None, {x_name: inp_x})

            if not outputs:
                return 0.0
            return _as_float(outputs[0])

        raise RuntimeError("Unsupported VAD model type.")

    def pad_chunk(self, chunk: np.ndarray) -> np.ndarray:
        """
        Pad ou tronque le chunk à la taille exacte attendue par Silero.
        """
        if not isinstance(chunk, np.ndarray):
            chunk = np.asarray(chunk, dtype=np.float32)
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32, copy=False)
        if chunk.ndim != 1:
            chunk = chunk.reshape(-1)

        n = int(self._chunk_samples)
        if n <= 0:
            return chunk
        if len(chunk) == n:
            return chunk
        if len(chunk) > n:
            return chunk[:n]

        padded = np.zeros(n, dtype=np.float32)
        padded[: len(chunk)] = chunk
        return padded

    def _remember_pre_roll(self, session: Session, chunk: np.ndarray) -> None:
        """
        Garde les derniers chunks de silence / bruit pour ne pas couper
        le début du premier mot au prochain speech_start.
        """
        if self._pre_roll_chunks <= 0:
            session.pre_speech_buffer.clear()
            return

        session.pre_speech_buffer.append(chunk.copy())
        while len(session.pre_speech_buffer) > self._pre_roll_chunks:
            session.pre_speech_buffer.popleft()

    def _flush_speech_start_buffer(self, session: Session) -> None:
        """
        Réinjecte un début de parole non confirmé dans le pré-roll.
        Cela évite de couper le début d'un mot si un chunk intermédiaire
        retombe brièvement sous le seuil.
        """
        if not session.speech_start_buffer:
            return
        for chunk in session.speech_start_buffer:
            self._remember_pre_roll(session, chunk)
        session.speech_start_buffer.clear()


def _as_float(value: object) -> float:
    """
    Convertit la sortie modèle (float / numpy / list) en float python.
    """
    try:
        if isinstance(value, (float, int)):
            return float(value)
        if isinstance(value, np.ndarray):
            return float(value.reshape(-1)[0]) if value.size else 0.0
        if isinstance(value, (list, tuple)) and value:
            return _as_float(value[0])
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return 0.0
