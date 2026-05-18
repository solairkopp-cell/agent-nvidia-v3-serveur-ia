#!/usr/bin/env python3
"""
CLI de test llama.cpp avec tool calls.
Usage: python llm_cli.py [--url URL] [--model MODEL]
"""

import asyncio
import json
import sys
import argparse
from typing import AsyncIterator

import httpx

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_URL   = "http://localhost:8080"
DEFAULT_MODEL = "default"

# ─── Faux tools (à adapter) ───────────────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "start_navigation",
            "description": "Starts GPS navigation to the current delivery.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_deliveries",
            "description": "Returns today's delivery list.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_navigation",
            "description": "Stops the current GPS navigation.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_map",
            "description": "Shows and recenters the map.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_photo",
            "description": "Asks the driver to take a proof-of-delivery photo.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

# ─── Implémentations mock ──────────────────────────────────────────────────────

TOOL_IMPLS = {
    "start_navigation": lambda **_: {"message": "Navigation started.", "trip_id": "TRIP_42"},
    "stop_navigation":  lambda **_: {"message": "Navigation stopped."},
    "show_map":         lambda **_: {"message": "Map shown and recentered."},
    "get_deliveries":   lambda **_: {
        "deliveries": [
            {"id": "T1", "client": "Alice", "address": "12 rue des Lilas, Paris", "status": "planned"},
            {"id": "T2", "client": "Bob",   "address": "5 avenue Victor Hugo, Lyon",  "status": "planned"},
        ]
    },
    "ask_photo": lambda **_: {"message": "photo_taken"},
}

# ─── Couleurs ANSI ─────────────────────────────────────────────────────────────

C = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "user":   "\033[36m",    # cyan
    "assist": "\033[32m",    # vert
    "tool":   "\033[33m",    # jaune
    "result": "\033[35m",    # magenta
    "error":  "\033[31m",    # rouge
    "info":   "\033[34m",    # bleu
}

def p(color, text, end="\n"):
    print(f"{C[color]}{text}{C['reset']}", end=end, flush=True)

# ─── Client llama.cpp ──────────────────────────────────────────────────────────

class LlamaCppClient:
    def __init__(self, base_url: str, model: str):
        self.url   = f"{base_url.rstrip('/')}/v1/chat/completions"
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, write=60.0, read=None, pool=60.0)
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()

    def _payload(self, messages, stream=False, tools=True):
        p = {"model": self.model, "messages": messages, "stream": stream}
        if tools:
            p["tools"] = TOOLS_SCHEMA
            p["tool_choice"] = "auto"
        return p

    async def complete(self, messages, tools=True) -> dict:
        client = await self._get_client()
        resp = await client.post(self.url, json=self._payload(messages, stream=False, tools=tools))
        resp.raise_for_status()
        return resp.json()

    async def stream(self, messages, tools=True) -> AsyncIterator[str]:
        """Yield text chunks; accumule les tool_calls et les retourne en dernier."""
        client = await self._get_client()
        assistant_parts = []
        tool_calls_by_index: dict = {}

        async with client.stream("POST", self.url, json=self._payload(messages, stream=True, tools=tools)) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    break

                data   = json.loads(raw)
                choice = (data.get("choices") or [{}])[0]
                delta  = choice.get("delta") or {}

                content = delta.get("content")
                if isinstance(content, str) and content:
                    assistant_parts.append(content)
                    if not tool_calls_by_index:
                        yield ("text", content)

                for td in delta.get("tool_calls") or []:
                    idx   = int(td.get("index", 0))
                    entry = tool_calls_by_index.setdefault(idx, {
                        "id": td.get("id", str(idx)),
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    })
                    if td.get("id"):
                        entry["id"] = td["id"]
                    fd = td.get("function") or {}
                    if fd.get("name"):
                        entry["function"]["name"] += fd["name"]
                    if fd.get("arguments"):
                        entry["function"]["arguments"] += fd["arguments"]

        if tool_calls_by_index:
            yield ("tool_calls", list(tool_calls_by_index.values()))
        else:
            yield ("done", "".join(assistant_parts))

# ─── Exécution des tools ───────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> dict:
    impl = TOOL_IMPLS.get(name)
    if impl:
        return impl(**args)
    return {"error": f"Unknown tool: {name}"}

# ─── Boucle principale ─────────────────────────────────────────────────────────

async def chat_loop(client: LlamaCppClient, stream: bool):
    history = [{"role": "system", "content": "You are Osias, a delivery driver voice assistant. Be concise."}]

    p("info", f"\n  llama.cpp tool-call tester  │  stream={'on' if stream else 'off'}")
    p("info",  "  Tools: " + ", ".join(t["function"]["name"] for t in TOOLS_SCHEMA))
    p("dim",   "  Ctrl-C ou 'exit' pour quitter\n")

    while True:
        # ── Input ──
        try:
            p("user", "You> ", end="")
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_input.lower() in ("exit", "quit", "q"):
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})
        messages = list(history)

        # ── Appel (stream ou non) avec résolution tool calls ──
        depth = 0
        MAX_ROUNDS = 8

        while depth < MAX_ROUNDS:
            p("assist", "Osias> ", end="")

            if stream:
                tool_calls = None
                full_text  = []

                async for event_type, payload in client.stream(messages):
                    print(f"DEBUG EVENT: {event_type} | {repr(payload)[:200]}")  # ← ajoute ça
                    if event_type == "text":
                        print(f"{C['assist']}{payload}{C['reset']}", end="", flush=True)
                        full_text.append(payload)
                    elif event_type == "tool_calls":
                        tool_calls = payload
                    # "done" → rien à faire

                print()  # newline après le stream

                if tool_calls:
                    # Affiche + exécute les tools
                    llm_msg = {
                        "role": "assistant",
                        "content": "".join(full_text),
                        "tool_calls": tool_calls,
                    }
                    messages.append(llm_msg)

                    for tc in tool_calls:
                        name = tc["function"]["name"]
                        args_raw = tc["function"].get("arguments", "{}")
                        try:
                            args = json.loads(args_raw) if args_raw.strip() else {}
                        except json.JSONDecodeError:
                            args = {}

                        p("tool",   f"  → tool_call: {name}({json.dumps(args)})")
                        result = execute_tool(name, args)
                        p("result", f"  ← result:    {json.dumps(result, ensure_ascii=False)}")

                        messages.append({
                            "role": "tool",
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False),
                            "tool_call_id": tc.get("id", "1"),
                        })

                    depth += 1
                    p("assist", "Osias> ", end="")
                    continue  # relance avec les tool results

                else:
                    # Réponse finale
                    final = "".join(full_text)
                    history.append({"role": "assistant", "content": final})
                    break

            else:
                # ── Non-stream ──
                try:
                    data    = await client.complete(messages)
                    msg     = data["choices"][0]["message"]
                    content = msg.get("content", "")
                    tcs     = msg.get("tool_calls") or []

                    if tcs:
                        print()  # newline pour le prompt
                        messages.append(msg)

                        for tc in tcs:
                            name = tc["function"]["name"]
                            args_raw = tc["function"].get("arguments", "{}")
                            try:
                                args = json.loads(args_raw) if args_raw.strip() else {}
                            except json.JSONDecodeError:
                                args = {}

                            p("tool",   f"  → tool_call: {name}({json.dumps(args)})")
                            result = execute_tool(name, args)
                            p("result", f"  ← result:    {json.dumps(result, ensure_ascii=False)}")

                            messages.append({
                                "role": "tool",
                                "name": name,
                                "content": json.dumps(result, ensure_ascii=False),
                                "tool_call_id": tc.get("id", "1"),
                            })

                        depth += 1
                        p("assist", "Osias> ", end="")
                        continue

                    else:
                        print(f"{C['assist']}{content}{C['reset']}")
                        history.append({"role": "assistant", "content": content})
                        break

                except Exception as e:
                    p("error", f"[ERREUR] {e}")
                    break

        else:
            p("error", "[MAX_ROUNDS atteint]")

    p("dim", "\nBye.")

# ─── Entrypoint ────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="llama.cpp tool-call CLI tester")
    parser.add_argument("--url",    default=DEFAULT_URL,   help=f"llama.cpp base URL (défaut: {DEFAULT_URL})")
    parser.add_argument("--model",  default=DEFAULT_MODEL, help=f"Nom du modèle (défaut: {DEFAULT_MODEL})")
    parser.add_argument("--no-stream", action="store_true", help="Désactive le streaming")
    args = parser.parse_args()

    client = LlamaCppClient(args.url, args.model)
    try:
        await chat_loop(client, stream=not args.no_stream)
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())