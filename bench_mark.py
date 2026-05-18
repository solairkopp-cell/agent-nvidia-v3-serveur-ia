#!/usr/bin/env python3
"""
Benchmark réaliste tool calls — simulation sorties Whisper STT
Usage: python bench_toolcalls.py [--url URL] [--model MODEL] [--no-stream]
"""

import asyncio
import json
import argparse
import httpx
from typing import Optional

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_URL   = "http://localhost:8080"
DEFAULT_MODEL = "default"
SYSTEM_PROMPT = "You are Osias, a delivery driver voice assistant. Be concise and tool-driven. Always call the appropriate tool when needed."

TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "start_navigation",  "description": "Starts GPS navigation to the current delivery.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "stop_navigation",   "description": "Stops the current GPS navigation.",              "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_deliveries",    "description": "Returns today's delivery list.",                 "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "show_map",          "description": "Shows and recenters the map.",                   "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "show_deliveries",   "description": "Displays the delivery list on the app UI.",      "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "ask_photo",         "description": "Asks the driver to take a proof-of-delivery photo.", "parameters": {"type": "object", "properties": {}}}},
]

# ─── Cas de test réalistes (simulation Whisper) ───────────────────────────────
# Format: (phrase, tool_attendu, difficulté, description)
# difficulté: 1=facile 2=moyen 3=difficile (transcription dégradée)

TEST_CASES = [

    # ── get_deliveries ────────────────────────────────────────────────────────
    ("how many stops do i have today",                      "get_deliveries", 1, "formulation naturelle"),
    ("what deliveries do i have",                           "get_deliveries", 1, "basique"),
    ("who's my next customer",                              "get_deliveries", 1, "client suivant"),
    ("what's the next address",                             "get_deliveries", 1, "adresse suivante"),
    ("how many stops i got",                                "get_deliveries", 2, "got instead of have"),
    ("whats my next drop",                                  "get_deliveries", 2, "argot livreur"),
    ("next delivery info",                                  "get_deliveries", 2, "ultra court"),
    ("tell me about my deliveries",                         "get_deliveries", 2, "indirect"),
    ("what am i delivering next",                           "get_deliveries", 2, "reformulation"),
    ("give me my schedule",                                 "get_deliveries", 2, "synonyme schedule"),
    ("how many stop i have to day",                         "get_deliveries", 3, "today splitté"),
    ("what's the adress for next one",                      "get_deliveries", 3, "faute adress"),
    ("whos my next costumer",                               "get_deliveries", 3, "faute costumer"),
    ("next deliv ery",                                      "get_deliveries", 3, "mot coupé"),
    ("uh what's my next stop uh",                           "get_deliveries", 3, "hésitations"),

    # ── start_navigation ─────────────────────────────────────────────────────
    ("start navigation",                                    "start_navigation", 1, "direct"),
    ("take me there",                                       "start_navigation", 1, "there implicite"),
    ("navigate to the next delivery",                       "start_navigation", 1, "explicite"),
    ("let's go",                                            "start_navigation", 1, "très court"),
    ("go to the next one",                                  "start_navigation", 2, "one implicite"),
    ("bring me to the customer",                            "start_navigation", 2, "bring instead of take"),
    ("start the gps",                                       "start_navigation", 2, "gps synonyme"),
    ("head to the next stop",                               "start_navigation", 2, "head to"),
    ("get me to the drop",                                  "start_navigation", 2, "argot drop"),
    ("start navig ation",                                   "start_navigation", 3, "mot coupé"),
    ("yeah let's go to the next one please",                "start_navigation", 3, "yeah + please"),
    ("um take me to uh the delivery",                       "start_navigation", 3, "hésitations"),
    ("go go navigation",                                    "start_navigation", 3, "répétition"),
    ("i need to go to the next customer now",               "start_navigation", 3, "phrase longue"),

    # ── stop_navigation ───────────────────────────────────────────────────────
    ("stop navigation",                                     "stop_navigation", 1, "direct"),
    ("cancel the route",                                    "stop_navigation", 1, "cancel"),
    ("i'm here",                                            "stop_navigation", 1, "arrivée implicite"),
    ("stop the gps",                                        "stop_navigation", 2, "gps synonyme"),
    ("i arrived",                                           "stop_navigation", 2, "arrivée"),
    ("end navigation",                                      "stop_navigation", 2, "end"),
    ("i don't need the route anymore",                      "stop_navigation", 2, "indirect"),
    ("stop navig",                                          "stop_navigation", 3, "tronqué Whisper"),
    ("yeah i'm here now stop",                              "stop_navigation", 3, "yeah + now"),
    ("uh stop the uh navigation please",                    "stop_navigation", 3, "hésitations"),

    # ── show_map ──────────────────────────────────────────────────────────────
    ("show me the map",                                     "show_map", 1, "direct"),
    ("open the map",                                        "show_map", 1, "open"),
    ("i'm lost",                                            "show_map", 2, "perdu implicite"),
    ("can you show the map",                                "show_map", 2, "can you"),
    ("i need to see where i am",                            "show_map", 2, "position"),
    ("where am i",                                          "show_map", 2, "position courte"),
    ("recenter",                                            "show_map", 2, "ultra court"),
    ("show me the mapp",                                    "show_map", 3, "faute mapp"),
    ("uh show map please",                                  "show_map", 3, "hésitation"),
    ("i can't find my way can you show the map",            "show_map", 3, "phrase longue"),

    # ── ask_photo ─────────────────────────────────────────────────────────────
    ("take a photo",                                        "ask_photo", 1, "direct"),
    ("i need proof of delivery",                            "ask_photo", 1, "preuve"),
    ("snap a picture",                                      "ask_photo", 2, "snap"),
    ("take a pic",                                          "ask_photo", 2, "pic raccourci"),
    ("i need to take a picture",                            "ask_photo", 2, "i need"),
    ("photo",                                               "ask_photo", 2, "ultra court"),
    ("take a foto",                                         "ask_photo", 3, "faute foto"),
    ("uh i need to take uh a photo",                        "ask_photo", 3, "hésitations"),
    ("take picture of the package please",                  "ask_photo", 3, "sans article"),

    # ── Pas de tool (réponses texte attendues) ────────────────────────────────
    ("okay",                                                None, 1, "acquiescement"),
    ("got it",                                              None, 1, "acquiescement"),
    ("thanks",                                              None, 1, "remerciement"),
    ("hello",                                               None, 1, "salutation"),
    ("the customer wasn't home",                            None, 2, "info état"),
    ("i left the package at the door",                      None, 2, "info état"),
    ("the address is wrong",                                None, 2, "problème"),
    ("uh yeah okay",                                        None, 3, "hésitation pure"),
    ("i i don't know",                                      None, 3, "confusion Whisper"),
]

ACCEPTABLE_ALTERNATIVES = {
    "show_deliveries": {"show_deliveries", "get_deliveries"},
    "get_deliveries":  {"get_deliveries",  "show_deliveries"},
    "stop_navigation": {"stop_navigation", "show_map"},
}

# ─── Couleurs ─────────────────────────────────────────────────────────────────

C = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "green": "\033[32m", "red": "\033[31m", "yellow": "\033[33m",
    "cyan": "\033[36m", "blue": "\033[34m", "magenta": "\033[35m",
}
def col(c, t): return f"{C[c]}{t}{C['reset']}"

# ─── Client ───────────────────────────────────────────────────────────────────

class Client:
    def __init__(self, url, model):
        self.url = f"{url.rstrip('/')}/v1/chat/completions"
        self.model = model
        self._c = httpx.AsyncClient(timeout=httpx.Timeout(connect=5, write=60, read=60, pool=60))

    async def close(self): await self._c.aclose()

    async def call(self, user_msg: str, stream: bool) -> tuple[Optional[str], str]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": TOOLS_SCHEMA,
            "tool_choice": "auto",
            "stream": stream,
        }

        if not stream:
            resp = await self._c.post(self.url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            msg  = data["choices"][0]["message"]
            tcs  = msg.get("tool_calls") or []
            return (tcs[0]["function"]["name"] if tcs else None), msg.get("content", "")

        tool_calls_by_index: dict = {}
        text_parts: list[str] = []
        async with self._c.stream("POST", self.url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"): continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]": break
                data   = json.loads(raw)
                choice = (data.get("choices") or [{}])[0]
                delta  = choice.get("delta") or {}
                if isinstance(delta.get("content"), str):
                    text_parts.append(delta["content"])
                for td in delta.get("tool_calls") or []:
                    idx   = int(td.get("index", 0))
                    entry = tool_calls_by_index.setdefault(idx, {"function": {"name": "", "arguments": ""}})
                    fd    = td.get("function") or {}
                    if fd.get("name"):      entry["function"]["name"]      += fd["name"]
                    if fd.get("arguments"): entry["function"]["arguments"] += fd["arguments"]

        if tool_calls_by_index:
            return tool_calls_by_index[0]["function"]["name"], ""
        return None, "".join(text_parts)

# ─── Benchmark ────────────────────────────────────────────────────────────────

async def run_bench(url: str, model: str, stream: bool):
    client = Client(url, model)

    print(f"\n{col('bold', '  llama.cpp tool-call benchmark — Whisper STT simulation')}")
    print(f"  url={url}  model={model}  stream={stream}")
    print(f"  {len(TEST_CASES)} cas  (difficulté: {col('cyan','1=facile')} {col('yellow','2=moyen')} {col('red','3=hard')})\n")

    by_difficulty: dict[int, list[bool]] = {1: [], 2: [], 3: []}
    by_tool: dict[str, list[bool]] = {}
    failures: list[tuple] = []
    total_ok = 0

    print(f"  {'PHRASE':<45} {'ATTENDU':<18} {'OBTENU':<18} {'D'} {'OK'}")
    print("  " + "─" * 90)

    for phrase, expected, diff, desc in TEST_CASES:
        try:
            got, content = await client.call(phrase, stream)
        except Exception as e:
            print(f"  {phrase:<45} {str(expected):<18} {'ERROR':<18} {diff} {col('red', '✗')}  {e}")
            by_difficulty[diff].append(False)
            by_tool.setdefault(expected or "none", []).append(False)
            failures.append((phrase, expected, "ERROR", desc, str(e)))
            continue

        acceptable = ACCEPTABLE_ALTERNATIVES.get(expected, {expected} if expected else {None})
        ok = got in acceptable

        if ok: total_ok += 1
        by_difficulty[diff].append(ok)
        by_tool.setdefault(expected or "none", []).append(ok)

        status  = col("green", "✓") if ok else col("red", "✗")
        got_str = got or col("dim", "(text)")
        exp_str = expected or col("dim", "(none)")
        diff_c  = {1: "cyan", 2: "yellow", 3: "red"}[diff]
        print(f"  {phrase:<45} {exp_str:<18} {got_str:<18} {col(diff_c, str(diff))} {status}")

        if not ok:
            failures.append((phrase, expected, got, desc, ""))

    await client.close()

    total = len(TEST_CASES)
    score = total_ok / total * 100

    print(f"\n  {'─'*90}")
    print(f"  {col('bold', 'PAR DIFFICULTÉ')}")
    for d, label, c in [(1, "1-facile", "cyan"), (2, "2-moyen ", "yellow"), (3, "3-hard  ", "red")]:
        bools = by_difficulty[d]
        n = len(bools); ok = sum(bools)
        pct = ok / n * 100 if n else 0
        bar = col("green", "█" * ok) + col("red", "░" * (n - ok))
        print(f"  {col(c, label)}  {bar}  {ok}/{n}  ({pct:.0f}%)")

    print(f"\n  {col('bold', 'PAR TOOL')}")
    for tool, bools in sorted(by_tool.items()):
        n = len(bools); ok = sum(bools)
        bar = col("green", "█" * ok) + col("red", "░" * (n - ok))
        print(f"  {tool:<20} {bar}  {ok}/{n}")

    color  = "green" if score >= 90 else "yellow" if score >= 75 else "red"
    rating = (
        col("green",  "✓ Production-ready")           if score >= 90 else
        col("yellow", "~ Acceptable avec supervision") if score >= 75 else
        col("red",    "✗ Pas prêt pour la prod")
    )
    print(f"\n  {col('bold', 'SCORE GLOBAL')}  {col(color, f'{total_ok}/{total}  ({score:.1f}%)')}  {rating}\n")

    if failures:
        print(f"  {col('red', 'ÉCHECS :')}")
        for phrase, expected, got, desc, err in failures:
            got_str = repr(got) if got else "(text)"
            print(f"  • [{desc}] {phrase!r}")
            print(f"    attendu={expected!r}  obtenu={got_str}  {err}")
    print()

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",       default=DEFAULT_URL)
    parser.add_argument("--model",     default=DEFAULT_MODEL)
    parser.add_argument("--no-stream", action="store_true")
    args = parser.parse_args()
    await run_bench(args.url, args.model, stream=not args.no_stream)

if __name__ == "__main__":
    asyncio.run(main())