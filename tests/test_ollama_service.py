import pytest
from unittest.mock import AsyncMock, MagicMock

import config
from services.ollama_service import OllamaService


def test_build_messages_uses_external_system_prompt(tmp_path, monkeypatch):
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("You are Rytle.", encoding="utf-8")
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(prompt_path))
    monkeypatch.setattr(config, "MAX_HISTORY", 3)

    service = OllamaService()
    messages = service.build_messages("Bonjour", [{"role": "assistant", "content": "Salut"}])

    assert messages[0] == {"role": "system", "content": "You are Rytle."}
    assert messages[-1] == {"role": "user", "content": "Bonjour"}


def test_build_messages_does_not_duplicate_last_user_message(tmp_path, monkeypatch):
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("You are Rytle.", encoding="utf-8")
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(prompt_path))

    service = OllamaService()
    history = [{"role": "user", "content": "Bonjour"}]

    messages = service.build_messages("Bonjour", history)

    assert messages.count({"role": "user", "content": "Bonjour"}) == 1


@pytest.mark.asyncio
async def test_chat_executes_tool_call_and_returns_final_content(tmp_path, monkeypatch):
    prompt_path = tmp_path / "system_prompt.md"
    prompt_path.write_text("You are Rytle.", encoding="utf-8")
    monkeypatch.setattr(config, "SYSTEM_PROMPT_PATH", str(prompt_path))

    service = OllamaService()
    service.set_ws_service(MagicMock(send=AsyncMock()))

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "show_map",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Map centered.",
                    }
                }
            ]
        },
    ]

    def fake_post(payload):
        return responses.pop(0)

    service._post_chat_completion = fake_post
    session = MagicMock()

    reply = await service.chat("show me the map", history=[], session=session)

    assert reply == "Map centered."
    service._ws_service.send.assert_awaited_once_with(
        session,
        {
            "type": "external_control",
            "action": "com.avvc.maps.action.RECENTER",
            "extras": {},
        },
    )
