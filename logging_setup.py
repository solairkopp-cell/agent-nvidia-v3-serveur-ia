from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path


class JsonlFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = traceback.format_exception(*record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_file_logging(*, log_file_path: str, level: str = "INFO") -> None:
    log_path = Path(log_file_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for h in root.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(log_path):
            return

    handler = logging.FileHandler(str(log_path), mode="a", encoding="utf-8")
    handler.setLevel(root.level)
    handler.setFormatter(JsonlFormatter())
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).propagate = True 