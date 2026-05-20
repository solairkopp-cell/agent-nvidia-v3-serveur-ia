import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator

import httpx
import requests

import config
from services.utility_service import UtilityService


logger = logging.getLogger(__name__)
DEFAULT_SYSTEM_PROMPT = ()


class OllamaService:
    def __init__(self, url=None, system_prompt_path=None):
        url = (url or config.OLLAMA_URL).rstrip("/")
        system_prompt_path = system_prompt_path or config.SYSTEM_PROMPT_PATH
        self.url = f"{url}/v1/chat/completions"
        self._base_url = url
        self._system_prompt_path = Path(system_prompt_path)
        self._extra_system_messages = []
        self.history = [{"role": "system", "content": self._load_system_prompt()}]
        self.status = "good"
        self._ws_service = None
        self._session = None
        self._async_client = None
        self.utility_service = UtilityService()

    # --- Lifecycle ---

    async def startup(self) -> None:
        try:
            for endpoint in ("/v1/models", "/api/tags"):
                response = requests.get(f"{self._base_url}{endpoint}", timeout=5)
                if response.status_code == 200:
                    logger.info("MascoteService démarré")
                    return
            raise RuntimeError("Ollama non joignable (healthcheck KO sur /v1/models et /api/tags)")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Ollama non joignable à {self._base_url}")

    async def shutdown(self) -> None:
        self._extra_system_messages = []
        self.history = [{"role": "system", "content": self._load_system_prompt()}]
        if self._async_client is not None:
            client = self._async_client
            self._async_client = None
            await client.aclose()
        logger.info("MascoteService arrêté")

    # --- Injection ---

    def set_ws_service(self, ws_service) -> None:
        self._ws_service = ws_service

    def set_session(self, session) -> None:
        self._session = session

    async def add_system_message(self, message: str, session=None) -> str:
        try:
            if session is not None:
                self.set_session(session)
            system_message = {"role": "user", "content": message}
            self._extra_system_messages.append(system_message)
            messages = list(self.history)
            messages.append(system_message)
            self.history = messages
            return await self._run_completion(messages, persist_history=True)
        except Exception as e:
            self.log(f"Erreur add_system_message : {e}", level="error")
            return "Erreur de connexion."

    async def generate_system_reply(self, system_message: str, user_message: str | None = None, session=None) -> AsyncIterator[str]:
        try:
            if session is not None:
                self.set_session(session)
            messages = list(self.history)
            messages.append({"role": "user", "content": system_message})
            if user_message is not None:
                messages.append({"role": "user", "content": user_message})
            async for chunk in self._run_completion_stream(messages, include_tools=False):
                yield chunk
        except Exception as e:
            self.log(f"Erreur generate_system_reply : {e}", level="error")
            yield "I could not process that."

    # --- Utilitaires ---

    def log(self, message, level="info"):
        if level == "error":
            logger.error(message)
            self.status = "bad"
        elif level == "warning":
            logger.warning(message)
            self.status = "medium"
        else:
            logger.info(message)

    def _load_system_prompt(self) -> str:
        try:
            prompt = self._system_prompt_path.read_text(encoding="utf-8").strip()
            if prompt:
                return prompt
            logger.warning("system_prompt.txt est vide, fallback sur le prompt par défaut")
        except FileNotFoundError:
            logger.warning("system_prompt.txt introuvable, fallback sur le prompt par défaut")
        except Exception as e:
            logger.warning(f"Erreur lecture system_prompt.txt : {e}")
        return DEFAULT_SYSTEM_PROMPT.__str__()

    # --- Les Outils ---

    async def start_navigation(self):
        resolved = self.utility_service.current_trip_id
        if not resolved:
            self.log("Action: START_NAVIGATION aborted — no planned delivery in data.json", level="warning")
            return {
                "error": "no_planned_delivery",
                "message": "No delivery with status planned in today's list.",
            }
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.START_NAVIGATION",
                "extras": {"id": resolved},
            })
        return {"message": f"Navigation started (trip {resolved}).", "trip_id": resolved}

    async def stop_navigation(self):
        self.log("Action: STOP_NAVIGATION")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.STOP_NAVIGATION",
                "extras": {},
            })
        return {"message": "the navigation has been stoped"}

    async def show_map(self):
        self.log("Action: RECENTER")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.RECENTER",
                "extras": {},
            })
        return {"message": "Map recentered and shown to the driver."}

    async def get_deliveries(self):
        self.log("Action: GET_DELIVERIES")
        return  self.utility_service.get_deliveries_summary()
    
    async def get_current_delivery_info(self):
        self.log("Action: GET_CURRENT_DELIVERY_INFO")
        return  self.utility_service.get_current_delivery_info()

    async def show_deliveries(self):
        self.log("Action: SHOW_DELIVERIES_LIST")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.SHOW_DELIVERIES_LIST",
                "extras": {},
            })
        return {"message": "Delivery list displayed on the map."}

    async def ask_photo(self):
        self.log("Action: ask_photo")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {"type": "ask_photo_event"})
        return {"message": "wait for message photo_taken or photo_failed"}

    def update_status(self, new_status):
        self.log(f"Action: Mise à jour du statut à {new_status}")
        self.status = new_status
        return {"message": f"Status updated to {new_status}."}

    # --- Schema ---

    def _get_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "start_navigation",
                    "description": (
                        "Starts GPS guidance to the current delivery "
                        "(the first planned one in the list, ignoring any trip_id from the LLM)."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_navigation",
                    "description": "Stops the current GPS guidance.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "show_map",
                    "description": (
                        "Shows the map to the driver and recenters it on his position. "
                        "Use when the driver wants to see the map without necessarily starting navigation."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_deliveries",
                    "description": (
                        "Returns the list of today's deliveries with details "
                        "(client name, package info, address) from data.json."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_current_delivery_info",
                    "description": (
                        "Returns information about the current delivery with details "
                        "(client name, package info, address, status) "
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "show_deliveries",
                    "description": (
                        "Displays the delivery list in the app UI. "
                        "Use only when the driver wants to see the list on screen."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "ask_photo",
                    "description": (
                        "Triggers the app to ask the driver to take a photo. "
                        "Use for proof of delivery or issue documentation. "
                        "Returns photo_taken or photo_failed."
                    ),
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ]

    # --- Cœur du service ---

    def build_messages(self, user_message, history=None):
        messages = [{"role": "system", "content": self._load_system_prompt()}]
        messages.extend(self._extra_system_messages)

        trimmed_history = list(history or [])
        max_history = max(0, int(getattr(config, "MAX_HISTORY", 0)))
        if max_history and len(trimmed_history) > max_history:
            trimmed_history = trimmed_history[-max_history:]

        for item in trimmed_history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"system", "user", "assistant", "tool"} and content is not None:
                messages.append({"role": role, "content": content})

        if not messages or messages[-1].get("role") != "user" or messages[-1].get("content") != user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    def _build_payload(self, messages, include_tools=True, stream=False):
        payload = {
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "stream": stream,
            "think": False,
        }
        if include_tools:
            payload["tools"] = self._get_tools_schema()
            payload["tool_choice"] = "auto"
        return payload

    def _post_chat_completion(self, payload):
        response = requests.post(self.url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, write=60.0, read=None, pool=60.0)
            )
        return self._async_client

    async def _request_completion(self, payload):
        return await asyncio.to_thread(self._post_chat_completion, payload)

    async def _execute_tool_calls(self, tool_calls):
        tool_messages = []

        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            args = tool_call["function"].get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args) if args.strip() else {}
            if args is None:
                args = {}

            tool_call_id = tool_call.get("id")
            if not tool_call_id:
                self.log(f"tool_call sans id pour '{func_name}'", level="warning")
                tool_call_id = str(hash(func_name))

            method = getattr(self, func_name, None)
            if method:
                result = await method(**args) if asyncio.iscoroutinefunction(method) else method(**args)
            else:
                result = {"error": f"Outil inconnu: {func_name}"}

            tool_messages.append({
                "role": "tool",
                "name": func_name,
                "content": json.dumps(result, ensure_ascii=False),
                "tool_call_id": tool_call_id,
            })

        return tool_messages

    async def _complete_tool_calls(self, messages, llm_message, include_tools=True, persist_history=False) -> str:
        conversation = list(messages)
        current_message = llm_message
        max_rounds = max(1, int(getattr(config, "MAX_TOOL_CALL_ROUNDS", 32)))

        for _ in range(max_rounds):
            tool_calls = current_message.get("tool_calls") or []
            if not (include_tools and tool_calls):
                if persist_history:
                    self.history = conversation + [current_message]
                return current_message.get("content") or ""

            tool_messages = await self._execute_tool_calls(tool_calls)
            conversation.extend([current_message] + tool_messages)

            next_res = await self._request_completion(
                self._build_payload(conversation, include_tools=include_tools)
            )
            current_message = next_res["choices"][0]["message"]

        self.log(f"MAX_TOOL_CALL_ROUNDS reached ({max_rounds})", level="warning")
        if persist_history:
            self.history = conversation + [current_message]
        return current_message.get("content") or ""

    async def _run_completion(self, messages, include_tools=True, persist_history=False):
        data = await self._request_completion(self._build_payload(messages, include_tools=include_tools))
        llm_message = data["choices"][0]["message"]

        if include_tools and llm_message.get("tool_calls"):
            return await self._complete_tool_calls(
                messages, llm_message,
                include_tools=include_tools,
                persist_history=persist_history,
            )

        if persist_history:
            self.history = messages + [llm_message]
        return llm_message.get("content") or ""

    async def _run_completion_stream(
        self,
        messages,
        include_tools=True,
        persist_history=False,
        depth=0,
    ) -> AsyncIterator[str]:
        client = await self._get_async_client()
        payload = self._build_payload(messages, include_tools=include_tools, stream=True)
        assistant_parts = []
        tool_calls_by_index = {}

        async with client.stream("POST", self.url, json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    break

                data = json.loads(raw)
                choices = data.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta") or {}

                content = delta.get("content")
                if isinstance(content, str) and content:
                    assistant_parts.append(content)
                    if not tool_calls_by_index:
                        yield content

                for tool_delta in delta.get("tool_calls") or []:
                    index = int(tool_delta.get("index", 0))
                    entry = tool_calls_by_index.setdefault(
                        index,
                        {
                            "id": tool_delta.get("id", ""),
                            "type": tool_delta.get("type", "function"),
                            "function": {"name": "", "arguments": ""},
                        },
                    )
                    if tool_delta.get("id"):
                        entry["id"] = tool_delta["id"]

                    func_delta = tool_delta.get("function") or {}
                    if name_piece := func_delta.get("name"):
                        entry["function"]["name"] += name_piece
                    if args_piece := func_delta.get("arguments"):
                        entry["function"]["arguments"] += args_piece

        if tool_calls_by_index:
            content_str = "".join(assistant_parts)
            llm_message = {
                "role": "assistant",
                "content": content_str or None,  # None quand tool_calls, conformément à la spec OpenAI/Qwen
                "tool_calls": [tool_calls_by_index[i] for i in sorted(tool_calls_by_index)],
            }
            max_rounds = max(1, int(getattr(config, "MAX_TOOL_CALL_ROUNDS", 32)))
            if depth >= max_rounds:
                self.log(f"MAX_TOOL_CALL_ROUNDS reached ({max_rounds}) in stream", level="warning")
                if persist_history:
                    self.history = messages + [llm_message]
                return

            tool_messages = await self._execute_tool_calls(llm_message["tool_calls"])
            new_messages = list(messages) + [llm_message] + tool_messages

            async for chunk in self._run_completion_stream(
                new_messages,
                include_tools=include_tools,
                persist_history=persist_history,
                depth=depth + 1,
            ):
                yield chunk
            return

        assistant_message = {"role": "assistant", "content": "".join(assistant_parts)}
        if persist_history:
            self.history = messages + [assistant_message]

    async def chat(self, user_message, history=None, session=None):
        try:
            if session is not None:
                self.set_session(session)
            messages = self.build_messages(user_message, history)
            return await self._run_completion(messages, persist_history=True)
        except Exception as e:
            self.log(f"Erreur : {e}", level="error")
            return "Erreur de connexion."

    async def stream_chat(self, user_message, history=None, session=None):
        emitted = False
        try:
            if session is not None:
                self.set_session(session)
            messages = self.build_messages(user_message, history)
            async for chunk in self._run_completion_stream(messages, persist_history=True):
                if chunk:
                    emitted = True
                    yield chunk
        except Exception as e:
            self.log(f"Erreur streaming : {e}", level="error")
            if not emitted:
                fallback = await self.chat(user_message, history=history, session=session)
                if fallback:
                    yield fallback