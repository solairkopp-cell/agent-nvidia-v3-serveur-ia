"""
tests/test_ollama_service.py
Tests unitaires de l'OllamaService.
"""
import config
import pytest
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


@pytest.mark.asyncio
async def test_generate_answer_stream_serializes_json_data(tmp_path, monkeypatch):
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("You are Rytle.", encoding="utf-8")
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(prompt_path))

    captured: dict = {}

    class FakeChunk:
        def __init__(self, response: str):
            self.response = response

    async def fake_stream():
        yield FakeChunk("Alice")

    class FakeClient:
        async def generate(self, **kwargs):
            captured.update(kwargs)
            return fake_stream()

    service = OllamaService()
    service._client = FakeClient()

    parts = []
    async for token in service.generate_answer_stream(
        [{"clientName": "Alice"}],
        "who is my next client?",
    ):
        parts.append(token)

    assert "".join(parts) == "Alice"
    assert '"clientName": "Alice"' in captured["prompt"]
    assert "who is my next client?" in captured["prompt"]
    assert captured["think"] is False
