# aiserver

**aiserver** est un serveur d'assistant vocal IA complet, conçu pour gérer des conversations en temps réel via WebRTC et WebSocket. Il intègre une pipeline complète allant de la réception audio à la synthèse vocale de la réponse.

---

## 🚀 Fonctionnalités

1. Reçoit de l'audio en temps réel via **WebRTC** / **WebSocket**
2. Détecte l'activité vocale (**VAD**) et débruite l'audio
3. Transcrit la parole en texte (**Whisper** - Speech-to-Text)
4. Détecte les **intentions** de l'utilisateur
5. Génère une réponse intelligente via un **LLM** (Ollama)
6. Synthétise la réponse en audio (**Piper TTS** - Text-to-Speech)

---

## 🗂️ Structure du projet

```
aiserver/
├── main.py                  # Point d'entrée du serveur
├── config.py                # Configuration générale
├── system_prompt.md         # Prompt système pour l'IA
├── requirements.txt         # Dépendances Python
│
├── services/                # Services principaux
│   ├── whisper_service.py   # Transcription audio (Speech-to-Text)
│   ├── piper_tts_service.py # Synthèse vocale (Text-to-Speech)
│   ├── ollama_service.py    # Inférence LLM via Ollama
│   ├── agent_service.py     # Orchestration de l'agent IA
│   ├── vad_service.py       # Détection d'activité vocale (VAD)
│   ├── denoise_service.py   # Débruitage audio
│   ├── audio_service.py     # Gestion audio générale
│   ├── webrtc_service.py    # Communication WebRTC
│   ├── websocket_service.py # Communication WebSocket
│   ├── intent_service.py    # Détection d'intentions
│   └── tts_utils.py         # Utilitaires TTS
│
├── intent_detection/        # Module de détection d'intentions
│   ├── intent_interview.py  # Logique de classification
│   └── intentions.csv       # Données d'intentions
│
├── models/                  # Modèles de données
│   ├── intent.py            # Modèle d'intention
│   └── session.py           # Modèle de session
│
├── web/                     # Interface utilisateur
│   └── index.html           # Page web principale
│
├── tests/                   # Tests unitaires
│   ├── test_agent_service.py
│   ├── test_audio_service.py
│   ├── test_denoise_service.py
│   ├── test_intent_interview.py
│   ├── test_ollama_service.py
│   ├── test_piper_service.py
│   ├── test_vad_service.py
│   └── test_webrtc_service.py
│
└── logs/                    # Fichiers de logs
```

---

## 🔧 Technologies utilisées

| Technologie | Rôle |
|---|---|
| [Whisper](https://github.com/openai/whisper) | Transcription audio (STT) |
| [Ollama](https://ollama.com/) | Inférence de modèles LLM en local |
| [Piper TTS](https://github.com/rhasspy/piper) | Synthèse vocale (TTS) |
| [aiortc](https://aiortc.readthedocs.io/) | Communication WebRTC |
| [websockets](https://websockets.readthedocs.io/) | Communication WebSocket |
| [PyTorch / torchaudio](https://pytorch.org/) | Traitement audio et ML |

---

## ⚙️ Installation

```bash
# Cloner le dépôt
git clone https://github.com/vivien-azonnoudo2002/aiserver.git
cd aiserver

# Installer les dépendances
pip install -r requirements.txt
```

---

## ▶️ Lancement

```bash
python main.py
```

L'interface web est accessible via le fichier `web/index.html`.

---

## 🧪 Tests

```bash
pytest tests/
```

---

## 🛑 Gestion des Interruptions (Barge-in)

Le serveur implémente un système complet d'interruption permettant à l'utilisateur de couper la parole à l'IA pendant qu'elle parle.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Utilisateur parle pendant que TTS joue                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. VAD détecte speech_start (chunks de 32ms)                    │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. agent.on_user_speech_start()                                 │
│    - Calcule le temps écoulé (elapsed_ms)                       │
│    - Positionne interruption_pending=True                       │
│    - Appelle interrupt()                                        │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. interrupt()                                                  │
│    - cancel_flag=True → annule le pipeline en cours             │
│    - tts_track.clear() → vide la queue TTS                      │
│    - Envoie {"type": "tts_stop_now"} au client                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. _decide_interruption_mode()                                  │
│    - continuation → fusion avec l'ancien message                │
│    - interruption → remplace l'ancien message                   │
└─────────────────────────────────────────────────────────────────┘
```

### Configuration

| Variable | Défaut | Description |
|----------|--------|-------------|
| `INTERRUPTION_SHORT_THRESHOLD_MS` | 1000 | Seuil temporel pour les interruptions courtes |
| `INTERRUPTION_WORDS_EN` | `no,stop,wait,cancel,forget,never mind` | Mots déclencheurs d'interruption |
| `CONTINUATION_WORDS_EN` | `also,and,plus,additionally,actually,wait and` | Mots de continuation |

### Logique de Décision

```python
if elapsed_ms < 1000ms:
    if mot_interruption:
        return "interruption"
    if mot_continuation:
        return "continuation"
    return "continuation"  # Par défaut
else:
    if mot_continuation:
        return "continuation"
    return "interruption"  # Par défaut
```

### Modes d'Interruption

| Mode | Comportement |
|------|--------------|
| **interruption** | Le message précédent est supprimé, nouveau tour de parole |
| **continuation** | Le nouveau texte est fusionné avec le message utilisateur actif |

### Événements WebSocket

| Type | Direction | Description |
|------|-----------|-------------|
| `vad: speech_start` | Server → Client | Détection de début de parole |
| `interruption_decision` | Server → Client | Décision (continuation/interruption) avec elapsed_ms |
| `tts_stop_now` | Server → Client | Arrêt immédiat du TTS |
| `interrupted` | Server → Client | Notification d'interruption |

### Fichiers Clés

| Fichier | Rôle |
|---------|------|
| `services/webrtc_service.py` | Détection VAD → `on_user_speech_start()` (ligne 405) |
| `services/agent_service.py` | Logique d'interruption (lignes 271-318, 567-583) |
| `models/session.py` | État d'interruption (`interruption_pending`, `elapsed_ms`) |
| `config.py` | Configuration des seuils et mots-clés (lignes 67-73) |

---

## 📄 Licence

Ce projet est open-source. Voir le fichier de licence pour plus de détails.
