"""
services/ollama_service.py
Client async vers Ollama (LLM local sur :11434).

Responsabilité :
  - Construire les messages (system prompt + historique + user input)
  - Appeler Ollama en mode streaming
  - Yielder les tokens au fur et à mesure pour alimenter le TTS
  - Gérer l'historique de conversation (trim)

Le system prompt définit la personnalité de l'agent.
"""
from __future__ import annotations

from typing import AsyncIterator

import config


SYSTEM_PROMPT = """You are a helpful voice assistant.
RULES:
- Respond in 1-2 short sentences maximum.
- Be direct and concise.
- Language: match the user's language.
- No markdown, no lists, no emojis.
"""


class OllamaService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._model: str = config.OLLAMA_MODEL
        # ollama.AsyncClient initialisé dans startup()
        self._client = None
        self._options: dict = {
            "num_ctx": config.OLLAMA_CONTEXT_WINDOW,
            "num_predict": config.OLLAMA_NUM_PREDICT,
            "temperature": config.OLLAMA_TEMPERATURE,
        }

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Initialiser le client ollama.AsyncClient.
        Vérifier que le modèle est disponible (ollama.list()).
        Si non disponible → lever une erreur claire au démarrage.
        """
        raise NotImplementedError

    async def shutdown(self):
        """Libérer les ressources."""
        raise NotImplementedError

    # ── Génération ───────────────────────────────────────────────────────────

    async def generate_stream(
        self,
        user_text: str,
        history: list[dict],
    ) -> AsyncIterator[str]:
        """
        Appel Ollama en mode streaming.

        Construit les messages :
          [{"role": "system", "content": SYSTEM_PROMPT}]
          + history[-N:]   (N = config.MAX_HISTORY)
          + [{"role": "user", "content": user_text}]

        Yield chaque token texte reçu du stream.

        En cas d'erreur réseau → yield "" et logger.

        Utilisé par AgentService pour alimenter KokoroPhraseService
        en temps réel (token par token).
        """
        raise NotImplementedError

    async def generate(
        self,
        user_text: str,
        history: list[dict],
    ) -> str:
        """
        Version non-streaming. Agrège tous les tokens.
        Utilisé pour les cas où le streaming n'est pas nécessaire.
        """
        raise NotImplementedError

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def build_messages(self, user_text: str, history: list[dict]) -> list[dict]:
        """
        Assemble le tableau de messages pour l'API Ollama.
        Tronque l'historique si nécessaire.
        """
        raise NotImplementedError

    async def health_check(self) -> bool:
        """
        Vérifier qu'Ollama répond et que le modèle est chargé.
        """
        raise NotImplementedError
