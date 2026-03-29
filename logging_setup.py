from __future__ import annotations

import logging
from pathlib import Path


def setup_file_logging(*, log_file_path: str, level: str = "INFO") -> None:
    """
    Ajoute un FileHandler (append) au root logger + loggers uvicorn.
    Safe à appeler plusieurs fois (évite les doublons).
    """
    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Éviter d'ajouter plusieurs fois le même handler.
    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(log_path):
            return

    handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    handler.setLevel(root.level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root.addHandler(handler)

    # Forcer les loggers uvicorn à propager vers root (pour capter access + error).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.propagate = True

