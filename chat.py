#!/usr/bin/env python3
import requests
import json

SYSTEM = """tu es rytle un assistant . ton role assister le livreur qui te parle .
pour donner des information par rapport à une livraison le tools_name est get_dleivery.
pour demarrer une livraison le tools_name est start_delivery.

regle 1: le tools_name doit etre remplis seulement si tu as besoin d'utiliser un outil pour repondre à la question du livreur.
regle 2: si tu n'as pas besoin d'utiliser un outil pour repondre à la question du livreur, le tools_name doit etre none.

"""
URL = "http://localhost:8080/completion"
history = []

def chat(user_input):
    history.append(f"<|im_start|>user\n{user_input}<|im_end|>")
    prompt = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n" + "\n".join(history) + "\n<|im_start|>assistant\n"
    
    r = requests.post(URL, json={"prompt": prompt, "stop": ["<|im_end|>"]})
    r.raise_for_status()
    
    content = r.json()["content"]
    data = json.loads(content)
    history.append(f"<|im_start|>assistant\n{content}<|im_end|>")
    return data

print("=== Rytle Chat === (Ctrl+C pour quitter)\n")
while True:
    try:
        user = input("Vous: ").strip()
        if not user:
            continue
        data = chat(user)
        print(f"Answer   : {data.get('answer', '')}")
        print(f"Tool     : {data.get('tool_name', '')}\n")
    except KeyboardInterrupt:
        print("\nBye.")
        break
    except Exception as e:
        print(f"Erreur: {e}\n")