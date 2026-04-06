"""
services/intent_service.py
Détection d'intentions via modèle finetuné local.

Responsabilité :
  - Charger l'embedder SentenceTransformers local finetuné
  - Charger le classifieur sklearn entraîné sur ces embeddings
  - Exposer une API simple : get_intent(text) / getint(text)
  - Optionnel : fournir detect() au format DetectedIntent (compat DI)
"""
from __future__ import annotations

import asyncio
import gc
import logging
import pickle
import sys
import types
import warnings
from pathlib import Path
from typing import Optional

import config
from models.intent import DetectedIntent


class IntentService:
    """
    Singleton optionnel. Peut être instancié dans main.py et injecté plus tard.
    """

    def __init__(self):
        self._csv_path: str = getattr(config, "INTENT_CSV_PATH", "intentions.csv")
        self._device: str = getattr(config, "INTENT_DEVICE", "auto")
        self._threshold: float = float(getattr(config, "INTENT_THRESHOLD", 0.40))
        self._model_dir = Path(
            getattr(
                config,
                "INTENT_MODEL_DIR",
                getattr(config, "INTENT_EMBED_LOCAL_DIR", "intent_detection2/intent_embedder"),
            )
        )
        self._classifier_path = Path(
            getattr(config, "INTENT_CLASSIFIER_PATH", "intent_detection2/intent_clf.pkl")
        )
        self._embedder = None
        self._classifier = None
        self._ready: bool = False
        self._logger = logging.getLogger(__name__)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Charger le modèle et le classifieur (bloquant → thread).
        """
        try:
            await asyncio.to_thread(self._startup_sync)
            self._ready = True
        except Exception:
            self._ready = False
            raise

    async def shutdown(self):
        """
        Libérer les ressources.
        """
        self._ready = False
        await asyncio.to_thread(self._shutdown_sync)

    def _startup_sync(self) -> None:
        self._embedder = self._load_embedder()
        self._classifier = self._load_classifier()
        self._logger.info(
            "Intent model loaded model_dir=%s classifier=%s threshold=%.2f",
            self._model_dir,
            self._classifier_path,
            self._threshold,
        )

    def _shutdown_sync(self) -> None:
        self._embedder = None
        self._classifier = None
        gc.collect()

        try:
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
        except Exception:
            pass

    def _load_embedder(self):
        try:
            import torch
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "Missing dependencies for intent detection. "
                "Install: sentence-transformers and torch."
            ) from exc

        if not self._model_dir.exists():
            raise FileNotFoundError(f"Intent model directory not found: {self._model_dir}")

        if self._device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self._device

        return SentenceTransformer(str(self._model_dir), device=device)

    def _load_classifier(self):
        if not self._classifier_path.exists():
            raise FileNotFoundError(f"Intent classifier not found: {self._classifier_path}")

        self._install_pickle_compat_aliases()

        with self._classifier_path.open("rb") as f:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                classifier = pickle.load(f)

        # Compat scikit-learn: certains pickles plus récents n'ont plus
        # explicitement cet attribut mais predict_proba en dépend encore ici.
        if not hasattr(classifier, "multi_class"):
            setattr(classifier, "multi_class", "auto")

        if not hasattr(classifier, "predict"):
            raise RuntimeError("Intent classifier does not implement predict().")
        if not hasattr(classifier, "classes_"):
            raise RuntimeError("Intent classifier does not expose classes_.")

        return classifier

    @staticmethod
    def _install_pickle_compat_aliases() -> None:
        """
        Compatibilité avec les pickles produits dans un autre environnement
        NumPy/scikit-learn.
        """
        try:
            import numpy.core.multiarray as multiarray
            import numpy.core.numeric as numeric
        except Exception:
            return

        pkg = sys.modules.get("numpy._core")
        if pkg is None:
            pkg = types.ModuleType("numpy._core")
            pkg.__path__ = []
            sys.modules["numpy._core"] = pkg

        sys.modules.setdefault("numpy._core.numeric", numeric)
        sys.modules.setdefault("numpy._core.multiarray", multiarray)

    def _encode(self, text: str):
        if self._embedder is None:
            raise RuntimeError("IntentService not started (startup() not called).")

        vector = self._embedder.encode([text], convert_to_numpy=True)
        if getattr(vector, "ndim", 0) == 1:
            vector = vector.reshape(1, -1)
        return vector

    def _predict_label_and_confidence(self, text: str) -> tuple[str, float]:
        if self._classifier is None:
            raise RuntimeError("IntentService not started (startup() not called).")

        vector = self._encode(text)
        label = str(self._classifier.predict(vector)[0])

        confidence = 1.0
        predict_proba = getattr(self._classifier, "predict_proba", None)
        if callable(predict_proba):
            try:
                probabilities = predict_proba(vector)[0]
                confidence = float(max(probabilities)) if len(probabilities) else 0.0
            except Exception:
                self._logger.exception("Intent classifier predict_proba failed; falling back to predicted label only")

        return label, confidence

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
        label, confidence = self._predict_label_and_confidence(text)
        if confidence < self._threshold:
            return "INCONNU"
        return label

    def get_intent(self, text: str) -> str:
        return self.getint(text)

    def predict_proba(self, text: str) -> dict[str, float]:
        """
        Expose les probabilités du classifieur pour debug/benchmark local.
        """
        text = (text or "").strip()
        if not text:
            return {}
        if not self._ready:
            raise RuntimeError("IntentService not started (startup() not called).")
        if self._classifier is None:
            return {}

        predict_proba = getattr(self._classifier, "predict_proba", None)
        if not callable(predict_proba):
            return {}

        vector = self._encode(text)
        probabilities = predict_proba(vector)[0]
        return {
            str(label): float(probability)
            for label, probability in zip(getattr(self._classifier, "classes_", []), probabilities)
        }

    async def detect(self, text: str, *, context: Optional[str] = None) -> DetectedIntent:
        """
        API optionnelle compatible avec le reste du serveur.
        Retourne DetectedIntent avec une seule intention.
        """
        intent = await asyncio.to_thread(self.getint, text)
        raw = {"intent": intent}
        if self._ready and (text or "").strip():
            try:
                raw["probabilities"] = await asyncio.to_thread(self.predict_proba, text)
            except Exception:
                self._logger.exception("Intent probabilities failed text=%r", text)
        intents = [] if intent == "INCONNU" else [intent]
        return DetectedIntent(context_ok=True, intents=intents, query_objects=[], raw=raw)

    async def health_check(self) -> bool:
        """
        True si le classifieur est chargé.
        """
        return self._ready
