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

import logging
from pathlib import Path
from typing import AsyncIterator

import config


DEFAULT_SYSTEM_PROMPT = """You are a helpful voice assistant.
Respond with short, direct, professional answers.
Do not use markdown, lists, or emojis.
"""


class OllamaService:
    """
    Singleton. Injecté dans AgentService.
    """

    def __init__(self):
        self._model: str = config.OLLAMA_MODEL
        # ollama.AsyncClient initialisé dans startup()
        self._client = None
        self._host: str = config.OLLAMA_URL
        self._system_prompt_path = Path(config.SYSTEM_PROMPT_PATH)
        self._system_prompt = self._load_system_prompt()
        self._options: dict = {
            "num_ctx": config.OLLAMA_CONTEXT_WINDOW,
            "num_predict": config.OLLAMA_NUM_PREDICT,
            "temperature": config.OLLAMA_TEMPERATURE,
            "presence_penalty": config.OLLAMA_PRESENCE_PENALTY,
            "repeat_penalty": config.OLLAMA_REPEAT_PENALTY,
            "top_k": config.OLLAMA_TOP_K,
            "top_p": config.OLLAMA_TOP_P,
            "stop": list(config.OLLAMA_STOP) if config.OLLAMA_STOP else None,
        }
        self._think = _parse_think(config.OLLAMA_THINK)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def startup(self):
        """
        Initialiser le client ollama.AsyncClient.
        Vérifier que le modèle est disponible (ollama.list()).
        Si non disponible → lever une erreur claire au démarrage.
        """
        logger = logging.getLogger(__name__)
        try:
            import ollama  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Dependency 'ollama' (python client) is not installed. Install requirements.txt."
            ) from exc

        self._client = ollama.AsyncClient(host=self._host)

        try:
            models = await self._client.list()
        except Exception as exc:
            raise RuntimeError(f"Ollama not reachable at {self._host}") from exc

        model_names = {m.model for m in getattr(models, "models", []) if getattr(m, "model", None)}
        if self._model not in model_names:
            available = ", ".join(sorted(model_names)) if model_names else "(none)"
            raise RuntimeError(
                f"Ollama model '{self._model}' not found. "
                f"Run `ollama pull {self._model}` or set OLLAMA_MODEL. Available: {available}"
            )
        logger.info(
            "System prompt loaded from %s (%d chars)",
            self._system_prompt_path,
            len(self._system_prompt),
        )

    async def shutdown(self):
        """Libérer les ressources."""
        # Le client ollama.AsyncClient ne nécessite pas de close explicite.
        self._client = None

    # ── Génération ───────────────────────────────────────────────────────────

    async def generate_stream(
        self,
        user_text: str,
        history: list[dict],
    ) -> AsyncIterator[str]:
        """
        Appel Ollama en mode streaming.

        Construit les messages :
          [{"role": "system", "content": self._system_prompt}]
          + history[-N:]   (N = config.MAX_HISTORY)
          + [{"role": "user", "content": user_text}]

        Yield chaque token texte reçu du stream.

        En cas d'erreur réseau → yield "" et logger.

        Utilisé par AgentService pour alimenter KokoroPhraseService
        en temps réel (token par token).
        """
        logger = logging.getLogger(__name__)
        if self._client is None:
            yield ""
            return

        messages = self.build_messages(user_text, history)
        try:
            stream = await self._client.chat(
                model=self._model,
                messages=messages,
                stream=True,
                think=self._think,
                options=self._options,
            )
            async for chunk in stream:
                msg = getattr(chunk, "message", None)
                content = getattr(msg, "content", None) if msg is not None else None
                if isinstance(content, str) and content:
                    yield content
        except Exception:
            logger.exception("Ollama generate_stream error")
            yield ""

    async def generate(
        self,
        user_text: str,
        history: list[dict],
    ) -> str:
        """
        Version non-streaming. Agrège tous les tokens.
        Utilisé pour les cas où le streaming n'est pas nécessaire.
        """
        parts: list[str] = []
        async for tok in self.generate_stream(user_text, history):
            if tok:
                parts.append(tok)
        return "".join(parts).strip()

    # ── Utilitaires ──────────────────────────────────────────────────────────

    def build_messages(self, user_text: str, history: list[dict]) -> list[dict]:
        """
        Assemble le tableau de messages pour l'API Ollama.
        Tronque l'historique si nécessaire.
        """
        messages: list[dict] = [{"role": "system", "content": self._system_prompt}]

        trimmed = history[-config.MAX_HISTORY :] if history else []
        for m in trimmed:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if isinstance(role, str) and isinstance(content, str):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_text})
        return messages

    async def health_check(self) -> bool:
        """
        Vérifier qu'Ollama répond et que le modèle est chargé.
        """
        if self._client is None:
            return False
        try:
            models = await self._client.list()
            model_names = {m.model for m in getattr(models, "models", []) if getattr(m, "model", None)}
            return self._model in model_names
        except Exception:
            return False

    def _load_system_prompt(self) -> str:
        """
        Charger le prompt système depuis un fichier texte/markdown.
        Fallback sur DEFAULT_SYSTEM_PROMPT si le fichier est absent ou vide.
        """
        logger = logging.getLogger(__name__)
        try:
            prompt = self._system_prompt_path.read_text(encoding="utf-8").strip()
            if prompt:
                return prompt
            logger.warning("System prompt file is empty: %s", self._system_prompt_path)
        except FileNotFoundError:
            logger.warning("System prompt file not found: %s", self._system_prompt_path)
        except Exception:
            logger.exception("Failed to load system prompt from %s", self._system_prompt_path)
        return DEFAULT_SYSTEM_PROMPT


def _parse_think(value: str):
    """
    Convertit la config OLLAMA_THINK (str) vers le type attendu par ollama.AsyncClient.chat().
    Valeurs supportées: true/false/low/medium/high.
    """
    v = (value or "").strip().lower()
    if v in ("", "none", "null"):
        return None
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("low", "medium", "high"):
        return v
    # fallback: garder bool False si valeur inconnue
    return False
