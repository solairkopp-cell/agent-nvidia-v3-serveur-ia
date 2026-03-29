"""
services/intent_service.py
Détection d'intentions via embeddings (SentenceTransformers).

Responsabilité :
  - Charger le classifieur d'intentions (IntentInterview basé sur un CSV)
  - Exposer une API simple : get_intent(text) / getint(text)
  - Optionnel : fournir detect() au format DetectedIntent (compat DI)
"""
from __future__ import annotations

import asyncio
from typing import Optional

import config
from intent_detection.intent_interview import IntentInterview
from models.intent import DetectedIntent


class IntentService:
    """
    Singleton optionnel. Peut être instancié dans main.py et injecté plus tard.
    """

    def __init__(self):
        self._csv_path: str = getattr(config, "INTENT_CSV_PATH", "intentions.csv")
        self._model_name: str = getattr(config, "INTENT_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
        self._device: str = getattr(config, "INTENT_DEVICE", "auto")
        self._threshold: float = float(getattr(config, "INTENT_THRESHOLD", 0.40))

        self._detector = IntentInterview(
            csv_path=self._csv_path,
            model_name=self._model_name,
            device=self._device,
            threshold=self._threshold,
        )
        self._ready: bool = False

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger le modèle et encoder les exemples (bloquant → thread).
        """
        try:
            await asyncio.to_thread(self._detector.startup)
            self._ready = True
        except Exception:
            self._ready = False
            raise

    async def shutdown(self):
        """
        Libérer les ressources.
        """
        self._ready = False
        await asyncio.to_thread(self._detector.shutdown)

    # ── Détection ────────────────────────────────────────────────────────────

    def getint(self, text: str) -> str:
        """
        API demandée : IntentService().getint(text) -> intent (str).
        """
        text = (text or "").strip()
        if not text:
            return "INCONNU"
        if not self._ready:
            raise RuntimeError("IntentService not started (startup() not called).")
        return self._detector.getint(text)

    def get_intent(self, text: str) -> str:
        return self.getint(text)

    async def detect(self, text: str, *, context: Optional[str] = None) -> DetectedIntent:
        """
        API optionnelle compatible avec le reste du serveur.
        Retourne DetectedIntent avec une seule intention.
        """
        intent = await asyncio.to_thread(self.getint, text)
        intents = [] if intent == "INCONNU" else [intent]
        return DetectedIntent(context_ok=True, intents=intents, query_objects=[], raw={"intent": intent})

    async def health_check(self) -> bool:
        """
        True si le classifieur est chargé.
        """
        return self._ready
