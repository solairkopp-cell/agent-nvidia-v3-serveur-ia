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

## 📄 Licence

Ce projet est open-source. Voir le fichier de licence pour plus de détails.
