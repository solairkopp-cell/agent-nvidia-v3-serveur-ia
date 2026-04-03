import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from models.session import Session
from services.action_service import ActionService


@pytest.fixture
def session():
    return Session(client_id="test-client", websocket=MagicMock())


@pytest.fixture
def action_service():
    service = ActionService()
    service._ws_service = MagicMock()
    service._ws_service.send = AsyncMock()
    return service


class TestKnownIntents:

    def test_removed_intents_are_not_known_anymore(self, action_service):
        assert "repeat_last_sentence" not in action_service._known_intents
        assert "stop_listening" not in action_service._known_intents
        assert "get_package_info" in action_service._known_intents
        assert "show_map" in action_service._known_intents


class TestGetPackageInfo:

    @pytest.mark.asyncio
    async def test_get_package_info_reads_first_planned_trip(self, action_service, session, tmp_path):
        data_file = tmp_path / "data.json"
        data_file.write_text(
            json.dumps(
                [
                    {
                        "id": "done-1",
                        "clientName": "Old",
                        "packageInfo": "Ignore me",
                        "deliveryStatus": "COMPLETED",
                    },
                    {
                        "id": "planned-1",
                        "clientName": "Alice",
                        "packageInfo": "Fragile medical supplies",
                        "deliveryStatus": "planned",
                    },
                    {
                        "id": "planned-2",
                        "clientName": "Bob",
                        "packageInfo": "Second package",
                        "deliveryStatus": "planned",
                    },
                ]
            ),
            encoding="utf-8",
        )
        action_service._data_file = data_file

        result = await action_service.execute(session, "get_package_info", "what is in the package")

        assert result.handled is True
        assert result.response == "Package info: Fragile medical supplies."


class TestShowMap:

    @pytest.mark.asyncio
    async def test_show_map_sends_recenter_event(self, action_service, session):
        result = await action_service.execute(session, "show_map", "show the map")

        assert result.handled is True
        assert result.response == "Centering the map."
        action_service._ws_service.send.assert_awaited_once_with(
            session,
            {
                "type": "external_control",
                "action": "com.avvc.maps.action.RECENTER",
                "extras": {},
            },
        )
