"""
tests/test_ollama_service.py
Tests unitaires de l'OllamaService.
"""
from pathlib import Path

import config
from services.ollama_service import OllamaService


def test_build_messages_uses_external_system_prompt(tmp_path, monkeypatch):
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("You are Rytle.", encoding="utf-8")
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(prompt_path))

    service = OllamaService()
    messages = service.build_messages("Bonjour", [{"role": "assistant", "content": "Salut"}])

    assert messages[0] == {"role": "system", "content": "You are Rytle."}
    assert messages[-1] == {"role": "user", "content": "Bonjour"}


def test_build_messages_falls_back_when_prompt_file_missing(tmp_path, monkeypatch):
    missing_path = tmp_path / "missing_system_prompt.md"
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(missing_path))

    service = OllamaService()
    messages = service.build_messages("Bonjour", [])

    assert messages[0]["role"] == "system"
    assert "helpful voice assistant" in messages[0]["content"]
