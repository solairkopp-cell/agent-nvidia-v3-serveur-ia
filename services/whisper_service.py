"""
services/whisper_service.py
STT via Whisper.

Responsabilité :
  - Mode "embedded" (recommandé) : charger faster-whisper dans le même process
  - Mode "http" : client HTTP vers un service Whisper externe
  - Retourner un TranscriptionResult (text + detected_language + duration_ms)

NB:
  - Pour le pipeline audio WebSocket, l'entrée optimale est du PCM (NumPy).
  - `transcribe(wav_bytes)` reste disponible pour compat / debug.
"""
from __future__ import annotations

import asyncio
import gc
import io
import logging
import sys
import time
from dataclasses import dataclass
from typing import Optional

import config


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None      # langue détectée par Whisper
    duration_ms: Optional[float] = None # durée du traitement


class WhisperService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._mode: str = config.WHISPER_MODE.lower().strip()
        self._url: str = config.WHISPER_URL
        self._timeout: int = config.WHISPER_TIMEOUT

        # Mode embedded
        self._backend: str = config.WHISPER_BACKEND.lower().strip()
        self._model_name: str = config.WHISPER_MODEL
        self._device: str = config.WHISPER_DEVICE
        self._compute_type: str = config.WHISPER_COMPUTE_TYPE
        self._beam_size: int = config.WHISPER_BEAM_SIZE
        self._model = None  # whisper.Whisper | faster_whisper.WhisperModel

        # Mode http
        self._client = None  # httpx.AsyncClient

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Initialiser Whisper selon le mode.
        - embedded : charger faster-whisper (bloquant → thread)
        - http     : créer client httpx + health check
        """
        if self._mode == "embedded":
            await self._startup_embedded()
            return
        if self._mode == "http":
            await self._startup_http()
            return
        raise RuntimeError(f"Unknown WHISPER_MODE='{self._mode}'. Use 'embedded' or 'http'.")

    async def shutdown(self):
        """Libérer les ressources."""
        if self._client is not None:
            client = self._client
            self._client = None
            await client.aclose()
        model = self._model
        self._model = None
        await asyncio.to_thread(self._cleanup_model_resources, model)

    # ── Transcription ─────────────────────────────────────────────────────────

    async def transcribe(self, wav_bytes: bytes) -> TranscriptionResult:
        """
        Transcrire un audio WAV (bytes en mémoire).
        - embedded : décode en NumPy et appelle faster-whisper
        - http     : multipart POST vers WHISPER_URL
        """
        if self._mode == "embedded":
            return await self._transcribe_embedded_wav(wav_bytes)
        if self._mode == "http":
            return await self._transcribe_http(wav_bytes)
        return TranscriptionResult(text="")

    async def transcribe_pcm(self, samples, sample_rate: int) -> TranscriptionResult:
        """
        Transcrire un signal audio PCM.

        - samples : np.ndarray float32 mono (ou multi-canal → moyenné)
        - sample_rate : fréquence d'échantillonnage (ex: 48000, 16000)

        En mode embedded, c'est l'API recommandée pour le flux audio.
        """
        if self._mode != "embedded":
            # En mode HTTP, il faudrait ré-encapsuler en WAV côté client.
            return TranscriptionResult(text="")
        return await self._transcribe_embedded_pcm(samples, sample_rate)

    async def health_check(self) -> bool:
        """
        embedded : True si le modèle est chargé
        http     : GET WHISPER_URL/
        """
        if self._mode == "embedded":
            return self._model is not None
        if self._mode == "http":
            try:
                return await self._health_check_http()
            except Exception:
                return False
        return False

    # ── Embedded backends ────────────────────────────────────────────────────

    async def _startup_embedded(self) -> None:
        if self._backend == "whisper":
            await self._startup_openai_whisper()
            return
        if self._backend == "faster-whisper":
            await self._startup_faster_whisper()
            return
        raise RuntimeError(f"Unknown WHISPER_BACKEND='{self._backend}'. Use 'whisper' or 'faster-whisper'.")

    async def _startup_openai_whisper(self) -> None:
        try:
            import whisper  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Dependency 'openai-whisper' is not installed (import name: whisper). "
                "Install requirements.txt."
            ) from exc

        def _load():
            return whisper.load_model(self._model_name, device=self._device)

        self._model = await asyncio.to_thread(_load)

    async def _startup_faster_whisper(self) -> None:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Dependency 'faster-whisper' is not installed. "
                "Install requirements.txt or switch WHISPER_BACKEND='whisper'."
            ) from exc

        def _load():
            return WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )

        self._model = await asyncio.to_thread(_load)

    async def _transcribe_embedded_wav(self, wav_bytes: bytes) -> TranscriptionResult:
        logger = logging.getLogger(__name__)
        import numpy as np
        import soundfile as sf

        start = time.perf_counter()
        try:
            samples, rate = sf.read(io.BytesIO(wav_bytes), dtype="float32", always_2d=False)
        except Exception:
            logger.exception("Whisper decode WAV failed")
            return TranscriptionResult(text="")

        # Déléguer au chemin PCM
        result = await self._transcribe_embedded_pcm(samples, int(rate) if rate else 16000)
        if result.duration_ms is None:
            result.duration_ms = (time.perf_counter() - start) * 1000.0
        return result

    async def _transcribe_embedded_pcm(self, samples, sample_rate: int) -> TranscriptionResult:
        logger = logging.getLogger(__name__)
        model = self._model
        if model is None:
            raise RuntimeError("WhisperService not started (startup() not called).")

        import numpy as np

        start = time.perf_counter()
        if not isinstance(samples, np.ndarray):
            samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=-1)
        samples = samples.astype(np.float32, copy=False).reshape(-1)

        # Whisper attend du 16kHz mono float32.
        if sample_rate and int(sample_rate) != 16000 and len(samples) > 0:
            samples = _resample_linear(samples, int(sample_rate), 16000)

        language = config.WHISPER_LANGUAGE or None

        if self._backend == "whisper":
            def _do_transcribe_openai():
                fp16 = str(self._device).startswith("cuda")
                kwargs = {"language": language, "fp16": fp16, "task": "transcribe"}
                # beam_size n'est pas supporté selon versions ; best-effort.
                try:
                    kwargs["beam_size"] = self._beam_size
                    result = model.transcribe(samples, **kwargs)
                except TypeError:
                    kwargs.pop("beam_size", None)
                    result = model.transcribe(samples, **kwargs)

                text = result.get("text", "") if isinstance(result, dict) else ""
                detected_language = result.get("language") if isinstance(result, dict) else None
                return str(text or "").strip(), detected_language if isinstance(detected_language, str) else None

            try:
                text, detected_language = await asyncio.to_thread(_do_transcribe_openai)
            except Exception:
                logger.exception("Whisper (openai) transcribe failed")
                return TranscriptionResult(text="")

        else:
            def _do_transcribe_faster():
                segments, info = model.transcribe(
                    samples,
                    language=language,
                    beam_size=self._beam_size,
                )
                text = "".join(getattr(seg, "text", "") for seg in segments).strip()
                detected_language = getattr(info, "language", None)
                return text, detected_language

            try:
                text, detected_language = await asyncio.to_thread(_do_transcribe_faster)
                
                # Garbage collection CUDA pour éviter l'OOM
                if str(self._device).startswith("cuda"):
                    import gc
                    gc.collect()
                    try:
                        import ctranslate2
                        # pas d'API cache à vider côté ctranslate2, gc suffit
                    except ImportError:
                        pass
            except Exception:
                logger.exception("Whisper (faster) transcribe failed")
                return TranscriptionResult(text="")

        duration_ms = (time.perf_counter() - start) * 1000.0
        return TranscriptionResult(text=text, language=detected_language, duration_ms=duration_ms)

    # ── HTTP mode (legacy) ───────────────────────────────────────────────────

    async def _startup_http(self) -> None:
        try: 
            import httpx
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Dependency 'httpx' is not installed. "
                "Install requirements.txt to enable WHISPER_MODE='http'."
            ) from exc

        self._client = httpx.AsyncClient(timeout=self._timeout)
        ok = await self._health_check_http()
        if not ok:
            raise RuntimeError(f"Whisper HTTP server not reachable at {self._url}")

    async def _health_check_http(self) -> bool:
        if self._client is None:
            return False
        resp = await self._client.get(self._url)
        return 200 <= resp.status_code < 500

    async def _transcribe_http(self, wav_bytes: bytes) -> TranscriptionResult:
        if self._client is None:
            raise RuntimeError("WhisperService not started (startup() not called).")

        import httpx

        start = time.perf_counter()
        try:
            resp = await self._client.post(
                self._url,
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={
                    "response_format": "verbose_json",
                    "language": config.WHISPER_LANGUAGE,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError, Exception):
            return TranscriptionResult(text="")

        text = data.get("text") if isinstance(data, dict) else ""
        lang = data.get("language") if isinstance(data, dict) else None
        duration = data.get("duration") if isinstance(data, dict) else None
        duration_ms = (time.perf_counter() - start) * 1000.0
        return TranscriptionResult(
            text=text or "",
            language=lang if isinstance(lang, str) else None,
            duration_ms=float(duration * 1000.0) if isinstance(duration, (int, float)) else duration_ms,
        )

    def _cleanup_model_resources(self, model) -> None:
        if model is None:
            return

        del model
        gc.collect()

        try:
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
        except Exception:
            pass


def _resample_linear(samples, source_rate: int, target_rate: int):
    import numpy as np

    if source_rate == target_rate:
        return samples.astype(np.float32, copy=False)
    if samples is None or len(samples) == 0:
        return np.array([], dtype=np.float32)

    samples = samples.astype(np.float32, copy=False)
    duration = len(samples) / float(source_rate)
    target_len = int(round(duration * target_rate))
    if target_len <= 0:
        return np.array([], dtype=np.float32)

    x_old = np.linspace(0.0, 1.0, num=len(samples), dtype=np.float32, endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=target_len, dtype=np.float32, endpoint=False)
    return np.interp(x_new, x_old, samples).astype(np.float32, copy=False)
