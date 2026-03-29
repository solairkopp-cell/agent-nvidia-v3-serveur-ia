"""
services/kokoro_tts_service.py
Synthèse vocale via Kokoro ONNX (local, no network).

Responsabilité :
  - Charger le modèle Kokoro ONNX une fois au démarrage
  - Découper le texte entrant en phrases (splitter)
  - Synthétiser chaque phrase et yielder les samples numpy
  - Gérer le look-ahead (synthèse N+1 pendant livraison de N)
  - Appliquer un fade-out lors d'une interruption

Protégé par asyncio.Lock : une seule synthèse à la fois
(le modèle ONNX n'est pas thread-safe).
"""
from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator, Optional

import numpy as np

import config


PUNCTUATION = set(",.!?:;")


def split_into_phrases(text: str) -> list[str]:
    """
    Découpe un texte en phrases sur la ponctuation.
    Protège les nombres décimaux (3.14 → non découpé).
    Filtre les fragments vides.
    """
    # Protéger les décimaux
    text = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)
    segments = re.split(r"([,.!?:;])", text)
    phrases = []
    for i in range(0, len(segments), 2):
        base = segments[i]
        punct = segments[i + 1] if i + 1 < len(segments) else ""
        phrase = (base + punct).strip().replace("<DOT>", ".")
        if phrase and not re.fullmatch(r"[,.!?:;]+", phrase):
            phrases.append(phrase)
    return phrases


class KokoroTTSService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._kokoro = None         # kokoro_onnx.Kokoro chargé dans startup()
        self._lock = asyncio.Lock() # protège le modèle ONNX
        self._voice: str = config.KOKORO_VOICE
        self._lang: str = config.KOKORO_LANG
        self._speed: float = config.KOKORO_SPEED

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger Kokoro depuis config.KOKORO_MODEL_PATH et KOKORO_VOICES_PATH.
        Le chargement est bloquant → exécuter dans asyncio.to_thread().
        Logger la durée de chargement.
        """
        raise NotImplementedError

    async def shutdown(self):
        """Libérer les ressources."""
        raise NotImplementedError

    # ── Synthèse ─────────────────────────────────────────────────────────────

    async def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """
        Synthétiser un texte complet.
        Retourne (samples float32, sample_rate).
        Protégé par self._lock.
        Exécuté dans asyncio.to_thread() pour ne pas bloquer la boucle.
        """
        raise NotImplementedError

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
        cancel_check: Optional[callable] = None,
    ) -> AsyncIterator[tuple[str, np.ndarray, int]]:
        """
        Mode streaming : consomme les tokens LLM au fur et à mesure.

        Algorithme :
          1. Accumuler les tokens dans un buffer
          2. Dès qu'une ponctuation est détectée → extraire la phrase
          3. Synthétiser la phrase (look-ahead : lancer N+1 pendant livraison de N)
          4. Yield (phrase_text, samples, sample_rate)
          5. Si cancel_check() → synthétiser fade-out des 3 premiers mots et stopper

        Yield : (phrase_text, audio_samples, sample_rate)
        """
        raise NotImplementedError

    async def synthesize_fade_out(self, text: str, duration_ms: int = 150) -> tuple[np.ndarray, int]:
        """
        Synthétiser les 3 premiers mots avec fade-out exponentiel.
        Utilisé lors d'une interruption pour une coupure naturelle.
        """
        raise NotImplementedError

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def apply_fade_out(self, samples: np.ndarray, rate: int, duration_ms: int = 200) -> np.ndarray:
        """
        Appliquer un fade-out exponentiel sur les N derniers ms.
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """
        Synthétiser une courte phrase de test.
        Retourne True si ça fonctionne.
        """
        raise NotImplementedError
