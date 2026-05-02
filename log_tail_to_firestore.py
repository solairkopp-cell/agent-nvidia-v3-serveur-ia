"""
log_tail_to_firestore.py
Lit server-logs.jsonl et pousse les nouvelles lignes vers Firestore toutes les 10s.

Structure Firestore :
  server_logs/{date}/sessions/{client_id}  → { logs: [...] }

Usage : python log_tail_to_firestore.py
"""
import json
import time
from collections import defaultdict
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import ArrayUnion

# ── Config ────────────────────────────────────────────────────────────────────
LOG_FILE = Path("logs/server-logs.jsonl")
CREDENTIALS_FILE = "firebase_credentials.json"
COLLECTION = "server_logs"
POLL_INTERVAL = 10  # secondes
# ─────────────────────────────────────────────────────────────────────────────

cred = credentials.Certificate(CREDENTIALS_FILE)
firebase_admin.initialize_app(cred)
db = firestore.client()


def tail_new_lines(file_path: Path, offset: int) -> tuple[list[dict], int]:
    lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        f.seek(offset)
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
        new_offset = f.tell()
    return lines, new_offset


def group_by_date_and_session(docs: list[dict]) -> dict:
    """
    Retourne { date: { client_id: [logs] } }
    Les logs sans client_id sont groupés sous "_server".
    """
    grouped = defaultdict(lambda: defaultdict(list))
    for doc in docs:
        ts = doc.get("ts", "")
        date = ts[:10] if len(ts) >= 10 else "unknown"
        # Extraire client_id depuis le msg si présent
        msg = doc.get("msg", "")
        client_id = "_server"
        if "client_id=" in msg:
            try:
                client_id = msg.split("client_id=")[1].split(" ")[0]
            except IndexError:
                pass
        grouped[date][client_id].append(doc)
    return grouped


def push_grouped(grouped: dict) -> int:
    """Push vers Firestore, retourne le nombre de logs envoyés."""
    total = 0
    for date, sessions in grouped.items():
        for client_id, logs in sessions.items():
            ref = db.collection(COLLECTION).document(date).collection("sessions").document(client_id)
            ref.set({"logs": ArrayUnion(logs)}, merge=True)
            total += len(logs)
    return total


def main() -> None:
    print(f"Watching {LOG_FILE} → Firestore/{COLLECTION}/{{date}}/sessions/{{client_id}}")
    offset = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0

    while True:
        time.sleep(POLL_INTERVAL)
        if not LOG_FILE.exists():
            continue

        current_size = LOG_FILE.stat().st_size
        if current_size < offset:
            offset = 0

        new_docs, offset = tail_new_lines(LOG_FILE, offset)
        if new_docs:
            grouped = group_by_date_and_session(new_docs)
            total = push_grouped(grouped)
            print(f"Pushed {total} log(s)")


if __name__ == "__main__":
    main()