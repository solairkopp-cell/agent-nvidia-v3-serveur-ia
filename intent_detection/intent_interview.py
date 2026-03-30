from __future__ import annotations

import gc
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass(slots=True)
class IntentResult:
    intent: str
    score: float


class IntentInterview:
    """
    Détection d'intentions via embeddings (SentenceTransformers).

    Usage (serveur) :
        detector = IntentInterview(csv_path="intentions.csv")
        intent = detector.getint("Je veux commander un café")

    Notes :
      - Charge le modèle et encode les exemples une seule fois.
      - La boucle interactive est disponible via `python intent.py`.
    """

    def __init__(
        self,
        *,
        csv_path: str = "",
        model_name: str = "paraphrase-multilingual-MiniLM-L12-v2",
        device: str = "auto",
        threshold: float = 0.40,
        local_dir: str = "",
        cache_dir: str = "",
        download_on_startup: bool = False,
    ):
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

        default_csv = Path(__file__).with_name("intentions.csv")
        self.csv_path = str(csv_path) if csv_path else str(default_csv)
        self.model_name = model_name
        self.device = device
        self.threshold = float(threshold)
        self.local_dir = str(local_dir or "").strip()
        self.cache_dir = str(cache_dir or "").strip()
        self.download_on_startup = bool(download_on_startup)

        self._model = None
        self._labels: list[str] = []
        self._examples: list[str] = []
        self._example_embeddings: Optional[np.ndarray] = None

    def startup(self) -> None:
        """
        Charger le modèle et encoder les exemples du CSV.
        Méthode sync (à lancer dans un thread si besoin).
        """
        logger = logging.getLogger(__name__)
        try:
            import torch
            import pandas as pd
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "Missing dependencies for intent detection. "
                "Install: sentence-transformers, torch, pandas."
            ) from exc

        if self.device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            device = self.device

        source, local_files_only = self._resolve_model_source()
        load_kwargs = {"device": device}
        if self.cache_dir:
            load_kwargs["cache_folder"] = self.cache_dir

        logger.info(
            "Intent model source=%s local_only=%s cache_dir=%s",
            source,
            local_files_only,
            self.cache_dir or "<default>",
        )
        model = SentenceTransformer(source, local_files_only=local_files_only, **load_kwargs)

        csv_file = Path(self.csv_path)
        if not csv_file.exists():
            raise FileNotFoundError(f"Intentions CSV not found: {self.csv_path}")

        df = pd.read_csv(csv_file)
        if "intent" not in df.columns or "example" not in df.columns:
            raise ValueError("intentions.csv must contain columns: intent, example")

        labels = df["intent"].astype(str).tolist()
        examples = df["example"].astype(str).tolist()

        example_embeddings = model.encode(
            examples,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        if not isinstance(example_embeddings, np.ndarray):
            example_embeddings = np.asarray(example_embeddings, dtype=np.float32)

        self._model = model
        self._labels = labels
        self._examples = examples
        self._example_embeddings = example_embeddings.astype(np.float32, copy=False)

    def _resolve_model_source(self) -> tuple[str, bool]:
        explicit_local = self._existing_model_dir(self.local_dir)
        if explicit_local is not None:
            return str(explicit_local), True

        cached_snapshot = self._find_local_snapshot(self.model_name, cache_dir=self.cache_dir)
        if cached_snapshot is not None:
            return str(cached_snapshot), True

        if self.download_on_startup:
            downloaded = self._download_model_snapshot()
            if downloaded is not None:
                return str(downloaded), True

        return self.model_name, False

    def _download_model_snapshot(self) -> Optional[Path]:
        try:
            from huggingface_hub import snapshot_download
        except Exception:
            return None

        kwargs = {
            "repo_id": self.model_name,
            "local_files_only": False,
        }
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir

        try:
            snapshot_path = snapshot_download(**kwargs)
        except Exception:
            logging.getLogger(__name__).exception("Intent model predownload failed repo=%s", self.model_name)
            return None
        return Path(snapshot_path)

    @staticmethod
    def _existing_model_dir(path_value: str) -> Optional[Path]:
        path = Path(path_value).expanduser() if path_value else None
        if path is None:
            return None
        if path.exists() and path.is_dir():
            return path
        return None

    @staticmethod
    def _find_local_snapshot(model_name: str, *, cache_dir: str = "") -> Optional[Path]:
        slug = model_name.replace("/", "--")
        candidates = IntentInterview._cache_roots(cache_dir)
        for root in candidates:
            repo_dir = root / f"models--{slug}"
            snapshot = IntentInterview._latest_snapshot(repo_dir)
            if snapshot is not None:
                return snapshot
        return None

    @staticmethod
    def _cache_roots(cache_dir: str = "") -> list[Path]:
        roots: list[Path] = []

        if cache_dir:
            base = Path(cache_dir).expanduser()
            if base.name == "hub":
                roots.append(base)
            else:
                roots.append(base / "hub")

        hf_home = os.getenv("HF_HOME", "").strip()
        if hf_home:
            roots.append(Path(hf_home).expanduser() / "hub")

        roots.append(Path.home() / ".cache" / "huggingface" / "hub")

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root)
            if key not in seen:
                seen.add(key)
                unique.append(root)
        return unique

    @staticmethod
    def _latest_snapshot(repo_dir: Path) -> Optional[Path]:
        snapshots_dir = repo_dir / "snapshots"
        if not snapshots_dir.exists():
            return None

        main_ref = repo_dir / "refs" / "main"
        if main_ref.exists():
            revision = main_ref.read_text(encoding="utf-8").strip()
            if revision:
                candidate = snapshots_dir / revision
                if candidate.exists():
                    return candidate

        snapshots = [path for path in snapshots_dir.iterdir() if path.is_dir()]
        if not snapshots:
            return None
        snapshots.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return snapshots[0]

    def classify(self, text: str, *, threshold: Optional[float] = None) -> IntentResult:
        """
        Retourne (intent, score). Si score < threshold → intent="INCONNU".
        """
        if self._model is None or self._example_embeddings is None:
            raise RuntimeError("IntentInterview not started (startup() not called).")

        thr = self.threshold if threshold is None else float(threshold)
        query_emb = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        if not isinstance(query_emb, np.ndarray):
            query_emb = np.asarray(query_emb, dtype=np.float32)
        query_emb = query_emb.astype(np.float32, copy=False).reshape(-1)

        scores = self._example_embeddings @ query_emb
        max_score = float(np.max(scores))
        best_idx = int(np.argmax(scores))

        if max_score < thr:
            return IntentResult(intent="INCONNU", score=max_score)
        return IntentResult(intent=self._labels[best_idx], score=max_score)

    def getint(self, text: str, *, threshold: Optional[float] = None) -> str:
        """
        API demandée : IntentInterview().getint(text) -> intent (str).
        """
        return self.classify(text, threshold=threshold).intent

    # Alias plus lisible
    def get_intent(self, text: str, *, threshold: Optional[float] = None) -> str:
        return self.getint(text, threshold=threshold)

    def shutdown(self) -> None:
        """
        Libérer explicitement le modèle et les embeddings.
        """
        self._model = None
        self._labels = []
        self._examples = []
        self._example_embeddings = None
        gc.collect()

        try:
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
        except Exception:
            pass


def _interactive() -> None:
    detector = IntentInterview()
    detector.startup()
    print(f"--- {len(detector._labels)} intentions chargées depuis le CSV ---")
    while True:
        phrase_user = input("\nUtilisateur : ")
        if phrase_user.lower() in ["exit", "quitter"]:
            break
        result = detector.classify(phrase_user)
        print(f"  -> Intention : {result.intent} (Score: {result.score:.2f})")


if __name__ == "__main__":
    _interactive()
