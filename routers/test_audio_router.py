"""
routers/test_audio_router.py
============================
Endpoint dédié aux tests de débruitage audio.

Route :
    POST /test/audio/session   → Enregistrer les métadonnées avant l'envoi de l'audio
    POST /test/audio/upload    → Recevoir l'audio, sauvegarder raw + denoised, transcrire, loguer le CSV

Stockage :
    Raw     → test_data/dennoise/records/raw/rawaudio_<N>.wav
    Denoised→ test_data/dennoise/records/denoised/denoised_<N>.wav
    CSV     → test_data/dennoise/records.csv

Le compteur N est global et auto-incrémenté (thread-safe via un verrou asyncio).
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# ── Chemins ────────────────────────────────────────────────────────────────────

_BASE_DIR     = Path("test_data/dennoise")
_RAW_DIR      = _BASE_DIR / "records" / "raw"
_DENOISED_DIR = _BASE_DIR / "records" / "denoised"
_CSV_PATH     = _BASE_DIR / "records.csv"

_CSV_HEADERS  = [
    "numero",
    "nom_driver",
    "texte_lu",
    "condition_lecture",
    "outil_debruitage",
    "chemin_raw",
    "chemin_denoised",
    "transcription",
]

# ── Compteur global auto-incrémenté ───────────────────────────────────────────

_counter_lock = asyncio.Lock()
_counter: int = 0          # sera re-calculé au 1er appel via _next_index()


async def _next_index() -> int:
    """
    Renvoie le prochain numéro disponible (1-based).
    Synchronisé pour éviter les collisions entre requêtes concurrentes.
    """
    global _counter
    async with _counter_lock:
        if _counter == 0:
            # Initialiser à partir des fichiers existants
            _counter = _scan_existing_index()
        _counter += 1
        return _counter


def _scan_existing_index() -> int:
    """Détermine le plus grand N déjà présent dans raw/ pour reprendre sans collision."""
    max_n = 0
    for f in _RAW_DIR.glob("rawaudio_*.wav"):
        try:
            n = int(f.stem.split("_", 1)[1])
            max_n = max(max_n, n)
        except (ValueError, IndexError):
            pass
    return max_n


# ── Helpers audio ──────────────────────────────────────────────────────────────

def _pcm16_to_float32(audio_bytes: bytes) -> np.ndarray:
    return np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def _float32_to_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (clipped * 32767.0).astype(np.int16).tobytes()


def _write_wav(path: Path, pcm_bytes: bytes, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)       # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def _read_wav_to_pcm16_bytes(wav_bytes: bytes) -> tuple[bytes, int]:
    """Lit un WAV en mémoire et renvoie (pcm_bytes_int16, sample_rate)."""
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sr


def _ensure_csv_header() -> None:
    """Crée le CSV avec entête s'il n'existe pas ou est vide."""
    _CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0:
        with _CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_HEADERS)


def _append_csv_row(row: dict) -> None:
    _ensure_csv_header()
    with _CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        writer.writerow(row)


# ── Routeur ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/test/audio", tags=["test-audio"])


@router.post("/upload")
async def upload_audio(
    # ── Métadonnées ──────────────────────────────────────────────────────────
    nom_driver:        str = Form(..., description="Nom du conducteur"),
    texte_lu:          str = Form(..., description="Texte que le conducteur devait lire"),
    condition_lecture: str = Form(..., description="Condition d'enregistrement (ex: silencieux, bruit route)"),
    outil_debruitage:  str = Form(..., description="Outil de débruitage utilisé (ex: RNNoise, DeepFilterNet, aucun)"),
    # ── Fichier audio ────────────────────────────────────────────────────────
    audio: UploadFile = File(..., description="Fichier audio (WAV PCM 16 kHz mono recommandé)"),
):
    """
    Reçoit métadonnées + audio, sauvegarde raw et denoised, transcrit avec Whisper.

    Formulaire multipart :
        nom_driver        : str
        texte_lu          : str
        condition_lecture : str
        outil_debruitage  : str
        audio             : file (wav/webm/ogg…)

    Réponse JSON :
        {
            "numero": N,
            "raw_path": "...",
            "denoised_path": "...",
            "transcription": "...",
        }
    """
    # ── Lire le fichier audio ────────────────────────────────────────────────
    try:
        raw_file_bytes = await audio.read()
    except Exception as exc:
        logger.error("Lecture du fichier audio échouée : %s", exc)
        raise HTTPException(status_code=400, detail=f"Impossible de lire le fichier audio : {exc}")

    if not raw_file_bytes:
        raise HTTPException(status_code=400, detail="Fichier audio vide")

    # ── Décoder en PCM int16 ─────────────────────────────────────────────────
    try:
        pcm_bytes_raw, sample_rate = _read_wav_to_pcm16_bytes(raw_file_bytes)
    except Exception:
        # Fichier non-WAV : on tente un décodage via soundfile
        try:
            import soundfile as sf  # type: ignore
            samples_f32, sample_rate = sf.read(io.BytesIO(raw_file_bytes), dtype="float32", always_2d=False)
            if samples_f32.ndim > 1:
                samples_f32 = samples_f32.mean(axis=-1)
            pcm_bytes_raw = _float32_to_pcm16(samples_f32)
        except Exception as exc2:
            logger.error("Décodage audio échoué : %s", exc2)
            raise HTTPException(status_code=422, detail=f"Format audio non supporté : {exc2}")

    samples_f32_raw = _pcm16_to_float32(pcm_bytes_raw)

    # ── Numéro d'enregistrement ──────────────────────────────────────────────
    n = await _next_index()

    # ── Chemins de sortie ────────────────────────────────────────────────────
    raw_path      = _RAW_DIR      / f"rawaudio_{n}.wav"
    denoised_path = _DENOISED_DIR / f"denoised_{n}.wav"

    # ── 1. Sauvegarder l'audio brut ──────────────────────────────────────────
    try:
        await asyncio.to_thread(_write_wav, raw_path, pcm_bytes_raw, sample_rate)
        logger.info("Raw audio saved → %s (%d bytes)", raw_path, raw_path.stat().st_size)
    except Exception as exc:
        logger.exception("Erreur sauvegarde raw audio")
        raise HTTPException(status_code=500, detail=f"Sauvegarde raw échouée : {exc}")

    # ── 2. Débruitage ────────────────────────────────────────────────────────
    # Import tardif pour éviter les dépendances circulaires au chargement du module
    try:
        from main import denoise_service  # type: ignore
        samples_f32_denoised = await denoise_service.process_utterance(
            samples_f32_raw, sample_rate=sample_rate
        )
        pcm_bytes_denoised = _float32_to_pcm16(samples_f32_denoised)
        logger.info("Denoise applied for record #%d", n)
    except Exception as exc:
        logger.warning("Débruitage échoué, fallback sur raw : %s", exc)
        # En cas d'échec, on sauvegarde le raw comme denoised (passthrough)
        pcm_bytes_denoised = pcm_bytes_raw

    try:
        await asyncio.to_thread(_write_wav, denoised_path, pcm_bytes_denoised, 16000)
        logger.info("Denoised audio saved → %s (%d bytes)", denoised_path, denoised_path.stat().st_size)
    except Exception as exc:
        logger.exception("Erreur sauvegarde denoised audio")
        raise HTTPException(status_code=500, detail=f"Sauvegarde denoised échouée : {exc}")

    # ── 3. Transcription Whisper ─────────────────────────────────────────────
    transcription = ""
    try:
        from main import whisper_service  # type: ignore
        result = await whisper_service.transcribe_pcm(samples_f32_denoised, 16000)
        transcription = result.text.strip()
        logger.info("Whisper transcription #%d : %r", n, transcription)
    except Exception as exc:
        logger.warning("Transcription Whisper échouée : %s", exc)

    # ── 4. Log CSV ───────────────────────────────────────────────────────────
    try:
        row = {
            "numero":            n,
            "nom_driver":        nom_driver,
            "texte_lu":          texte_lu,
            "condition_lecture": condition_lecture,
            "outil_debruitage":  outil_debruitage,
            "chemin_raw":        str(raw_path),
            "chemin_denoised":   str(denoised_path),
            "transcription":     transcription,
        }
        await asyncio.to_thread(_append_csv_row, row)
        logger.info("CSV row #%d written to %s", n, _CSV_PATH)
    except Exception as exc:
        logger.exception("Erreur écriture CSV")
        # Non-bloquant : on retourne quand même le résultat

    # ── Réponse ──────────────────────────────────────────────────────────────
    return JSONResponse({
        "numero":          n,
        "raw_path":        str(raw_path),
        "denoised_path":   str(denoised_path),
        "transcription":   transcription,
        "nom_driver":      nom_driver,
        "texte_lu":        texte_lu,
        "condition_lecture": condition_lecture,
        "outil_debruitage":  outil_debruitage,
    })


@router.get("/records")
async def list_records():
    """
    Retourne le contenu du CSV sous forme de liste JSON.
    """
    if not _CSV_PATH.exists() or _CSV_PATH.stat().st_size == 0:
        return JSONResponse({"records": []})

    records = []
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    return JSONResponse({"records": records})
