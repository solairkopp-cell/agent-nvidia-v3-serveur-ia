import asyncio
import requests
import logging
import json
from pathlib import Path

import config

logging.basicConfig(
    filename='mascote.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DEFAULT_SYSTEM_PROMPT = (
    "Tu es Rytle, un assistant de livraison poli et efficace. "
    "**regles**: 1) verifie toujours que les info necessaires à l'appel d'un outil "
    "ne sont pas deja dans l'historique de la conversation avant de demander à l'utilisateur."
)


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

    # --- Lifecycle ---

    async def startup(self) -> None:
        try:
            for endpoint in ("/v1/models", "/api/tags"):
                response = requests.get(f"{self._base_url}{endpoint}", timeout=5)
                if response.status_code == 200:
                    logging.info("MascoteService démarré")
                    return
            raise RuntimeError("Ollama non joignable (healthcheck KO sur /v1/models et /api/tags)")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Ollama non joignable à {self._base_url}")

    async def shutdown(self) -> None:
        self._extra_system_messages = []
        self.history = [{"role": "system", "content": self._load_system_prompt()}]
        logging.info("MascoteService arrêté")

    # --- Injection ---

    def set_ws_service(self, ws_service) -> None:
        self._ws_service = ws_service

    def set_session(self, session) -> None:
        self._session = session

    async def add_system_message(self, message: str, session=None) -> str:
        try:
            if session is not None:
                self.set_session(session)

            system_message = {"role": "system", "content": message}
            self._extra_system_messages.append(system_message)
            messages = list(self.history)
            messages.append(system_message)
            self.history = messages
            return await self._run_completion(messages, persist_history=True)

        except Exception as e:
            self.log(f"Erreur add_system_message : {e}", level="error")
            return "Erreur de connexion."

    async def generate_system_reply(self, system_message: str, user_message: str | None = None, session=None) -> str:
        try:
            if session is not None:
                self.set_session(session)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You speak directly to a delivery driver. "
                        "Reply in short, natural English. "
                        "Use at most two short sentences."
                    ),
                },
                {"role": "system", "content": system_message},
            ]

            if user_message is not None:
                messages.append({"role": "user", "content": user_message})

            return await self._run_completion(messages, include_tools=False)
        except Exception as e:
            self.log(f"Erreur generate_system_reply : {e}", level="error")
            return "I could not process that."

    async def is_this_a_confirmation(self, message: str, session=None) -> bool:
        try:
            if session is not None:
                self.set_session(session)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You classify a delivery driver's answer to the question "
                        "'Is the delivery completed?'. "
                        "Reply only with true or false. "
                        "Reply true only if the driver clearly confirms completion. "
                        "Reply false for no, doubt, refusal, requests for help, "
                        "or any unclear answer."
                    ),
                },
                {"role": "user", "content": message},
            ]

            reply = await self._run_completion(messages, include_tools=False)
            return reply.strip().lower().startswith("true")
        except Exception as e:
            self.log(f"Erreur is_this_a_confirmation : {e}", level="error")
            return False

    async def get_delivery_failure_reason_response(
        self,
        message: str,
        reasons: list[str] | tuple[str, ...],
        session=None,
    ) -> str:
        try:
            if session is not None:
                self.set_session(session)

            numbered_reasons = "\n".join(
                f"{index}. {reason}"
                for index, reason in enumerate(reasons, start=1)
            )
            max_reason = len(reasons)

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You analyze a delivery driver's answer after they were asked "
                        "to choose a failure reason.\n"
                        f"Available reasons are:\n{numbered_reasons}\n"
                        "Rules:\n"
                        f"- If the driver clearly chooses one reason, reply only with a number between 1 and {max_reason}.\n"
                        "- If the driver asks for the list, options, or reasons, reply only with the numbered list.\n"
                        "- If the driver says the reason itself instead of the number, map it to the right number.\n"
                        f"- If the answer is unclear, reply only with: Please choose a number between 1 and {max_reason} or ask for the list."
                    ),
                },
                {"role": "user", "content": message},
            ]

            return await self._run_completion(messages, include_tools=False)
        except Exception as e:
            self.log(f"Erreur get_delivery_failure_reason_response : {e}", level="error")
            return f"Please choose a number between 1 and {len(reasons)} or ask for the list."

    # --- Utilitaires ---

    def log(self, message, level="info"):
        if level == "error":
            logging.error(message)
            self.status = "bad"
        elif level == "warning":
            logging.warning(message)
            self.status = "medium"
        else:
            logging.info(message)

    def _load_system_prompt(self) -> str:
        try:
            prompt = self._system_prompt_path.read_text(encoding="utf-8").strip()
            if prompt:
                return prompt
            logging.warning("system_prompt.txt est vide, fallback sur le prompt par défaut")
        except FileNotFoundError:
            logging.warning("system_prompt.txt introuvable, fallback sur le prompt par défaut")
        except Exception as e:
            logging.warning(f"Erreur lecture system_prompt.txt : {e}")
        return DEFAULT_SYSTEM_PROMPT

    # --- Les Outils ---

    def get_delivery_info(self, order_id):
        self.log(f"Action: Récupération des données pour le colis {order_id}")
        db = {
            "ABC-123": {"status": "En livraison", "secteur": "Ariana", "client": "Ahmed"},
            "XYZ-789": {"status": "Livré", "secteur": "La Marsa", "client": "Sonia"}
        }
        return db.get(order_id, {"error": "Colis introuvable"})

    async def start_navigation(self, trip_id: str):
        self.log(f"Action: START_NAVIGATION trip_id={trip_id}")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.START_NAVIGATION",
                "extras": {"id": trip_id},
            })
        return {"message": f"Navigation démarrée (trip {trip_id})."}

    async def stop_navigation(self):
        self.log("Action: STOP_NAVIGATION")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.STOP_NAVIGATION",
                "extras": {},
            })
        return {"message": "Navigation arrêtée."}

    async def show_map(self):
        self.log("Action: RECENTER")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.RECENTER",
                "extras": {},
            })
        return {"message": "Carte recentrée."}

    async def get_deliveries(self):
        self.log("Action: SHOW_DELIVERIES_LIST")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {
                "type": "external_control",
                "action": "com.avvc.maps.action.SHOW_DELIVERIES_LIST",
                "extras": {},
            })
        try:
            with open('data.json', 'r', encoding='utf-8') as f:
                deliveries = json.load(f)
            return {"deliveries": deliveries}
        except FileNotFoundError:
            return {"deliveries": []}
        except json.JSONDecodeError:
            return {"deliveries": []}

    async def ask_photo(self):
        self.log("Action: ask_photo")
        if self._ws_service and self._session:
            await self._ws_service.send(self._session, {"type": "ask_photo_event"})
        return {"message": "wait for message photo_taken or photo_failed"}

    def update_status(self, new_status):
        self.log(f"Action: Mise à jour du statut à {new_status}")
        self.status = new_status
        return {"message": f"Statut mis à jour à {new_status}."}

    # --- Schema ---

    def _get_tools_schema(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_delivery_info",
                    "description": "Récupère les infos d'un colis spécifique (statut, secteur, client).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "L'identifiant du colis (ex: ABC-123)"}
                        },
                        "required": ["order_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "start_navigation",
                    "description": "Lance le GPS vers une destination via son ID de planning.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "trip_id": {"type": "string", "description": "L'identifiant du trip de livraison"}
                        },
                        "required": ["trip_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_navigation",
                    "description": "Arrête le guidage GPS en cours.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "show_map",
                    "description": "Recentre la carte sur la position actuelle.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_deliveries",
                    "description": "Liste toutes les livraisons prévues pour aujourd'hui.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "ask_photo",
                    "description": "Demande au livreur de prendre une photo de preuve de livraison.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_status",
                    "description": "Change le statut de la livraison actuelle.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "new_status": {"type": "string", "description": "Le nouveau statut (ex: Livré, Absent, Problème)"}
                        },
                        "required": ["new_status"]
                    }
                }
            }
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

    def _build_payload(self, messages, include_tools=True):
        payload = {
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "temperature": config.OLLAMA_TEMPERATURE,
        }
        if include_tools:
            payload["tools"] = self._get_tools_schema()
            payload["tool_choice"] = "auto"
        return payload

    def _post_chat_completion(self, payload):
        response = requests.post(self.url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()

    async def _run_completion(self, messages, include_tools=True, persist_history=False):
        data = self._post_chat_completion(self._build_payload(messages, include_tools=include_tools))
        llm_message = data["choices"][0]["message"]

        if include_tools and llm_message.get("tool_calls"):
            tool_messages = [llm_message]

            for tool_call in llm_message["tool_calls"]:
                func_name = tool_call["function"]["name"]
                args = tool_call["function"].get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                if args is None:
                    args = {}

                method = getattr(self, func_name, None)
                if method:
                    result = await method(**args) if asyncio.iscoroutinefunction(method) else method(**args)
                else:
                    result = {"error": f"Outil inconnu: {func_name}"}

                tool_messages.append({
                    "role": "tool",
                    "name": func_name,
                    "content": json.dumps(result, ensure_ascii=False),
                    "tool_call_id": tool_call.get("id", "1")
                })

            final_messages = messages + tool_messages
            final_res = self._post_chat_completion(
                self._build_payload(final_messages, include_tools=include_tools)
            )
            final_message = final_res["choices"][0]["message"]
            if persist_history:
                self.history = final_messages + [final_message]
            return final_message.get("content", "")

        if persist_history:
            self.history = messages + [llm_message]
        return llm_message.get("content", "")

    async def chat(self, user_message, history=None, session=None):
        try:
            if session is not None:
                self.set_session(session)

            messages = self.build_messages(user_message, history)
            return await self._run_completion(messages, persist_history=True)

        except Exception as e:
            self.log(f"Erreur : {e}", level="error")
            return "Erreur de connexion."
