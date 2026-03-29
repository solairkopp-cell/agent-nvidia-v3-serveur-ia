"""
models/intent.py
Structures de données pour la détection d'intentions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class QueryObject:
    """
    Objet extrait de la requête utilisateur.

    Exemple : {"name": "product", "value": "iPhone 15"}.
    """
    name: str
    value: Optional[str] = None


@dataclass(slots=True)
class DetectedIntent:
    """
    Résultat final renvoyé par IntentService.
    """
    context_ok: bool
    intents: list[str] = field(default_factory=list)
    query_objects: list[QueryObject] = field(default_factory=list)
    # Payload brut optionnel (utile pour debug / observabilité)
    raw: Optional[dict[str, Any]] = None

