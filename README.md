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

## 🎙️ Synthèse Vocale (TTS)

### Voix configurée

| Paramètre | Valeur |
|-----------|--------|
| **Modèle** | `en_US-ljspeech-high.onnx` |
| **Langue** | Anglais (US) 🇺🇸 |
| **Voix** | LJSpeech (féminine) |
| **Qualité** | High (meilleure qualité, ~100-150 MB) |

---

## 🔊 Choix de la Voix TTS

### Pourquoi choisir une voix ?

Le choix de la voix TTS impacte plusieurs aspects de ton application :

| Critère | Impact |
|---------|--------|
| **Qualité audio** | Une voix *high* est plus naturelle et expressive |
| **Taille du modèle** | De 15 MB (x_low) à 120 MB (high) |
| **Consommation CPU** | Les modèles lourds demandent plus de ressources |
| **Latence** | Plus le modèle est lourd, plus la synthèse est lente |
| **Usage** | Embarqué (low) vs Serveur (high) |

### Comparaison des qualités

| Qualité | Taille | CPU | Latence | Usage recommandé |
|---------|--------|-----|---------|------------------|
| **x_low** | ~15 MB | Très faible | ~50ms | IoT, Raspberry Pi, mobile |
| **low** | ~20 MB | Faible | ~80ms | Applications temps réel |
| **medium** | ~60 MB | Moyen | ~120ms | Serveur, desktop |
| **high** | ~120 MB | Élevé | ~200ms | Production, qualité maximale |

### Comment choisir ?

| Besoin | Qualité recommandée | Exemple |
|--------|---------------------|---------|
| **Prototype rapide** | `low` | Tests, démos |
| **Application mobile** | `low` ou `medium` | Batterie limitée |
| **Serveur vocal** | `medium` ou `high` | Qualité importante |
| **Embarqué (Jetson, Pi)** | `low` | Ressources limitées |
| **Production** | `high` | Meilleure expérience utilisateur |

### Voix configurée actuellement

```
en_US-ljspeech-high
├── Langue: Anglais (US) 🇺🇸
├── Locuteur: LJSpeech (féminin)
├── Qualité: High
├── Taille: ~120 MB
└── Sample Rate: 22050 Hz
```

### Changer de voix

1. **Télécharger** une voix depuis [Hugging Face - Piper Voices](https://huggingface.co/rhasspy/piper-voices)
2. **Placer** les fichiers `.onnx` et `.onnx.json` dans `assets/models/`
3. **Modifier** `.env` :
   ```bash
   PIPER_MODEL_PATH="assets/models/en_US-ljspeech-high.onnx"
   PIPER_CONFIG_PATH="assets/models/en_US-ljspeech-high.onnx.json"
   ```
4. **Redémarrer** le serveur

### Voix recommandées par langue

| Langue | Voix | Qualité | Taille | Lien |
|--------|------|---------|--------|------|
| 🇺🇸 Anglais | `en_US-ljspeech-high` | High | ~120 MB | [Télécharger](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/high) |
| 🇺🇸 Anglais | `en_US-danny-low` | Low | ~20 MB | [Télécharger](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/danny/low) |
| 🇫🇷 Français | `fr_FR-siwis-medium` | Medium | ~60 MB | [Télécharger](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/siwis/medium) |
| 🇩🇪 Allemand | `de_DE-thorsten-medium` | Medium | ~60 MB | [Télécharger](https://huggingface.co/rhasspy/piper-voices/tree/main/de/de_DE/thorsten/medium) |
| 🇪🇸 Espagnol | `es_ES-davefx-medium` | Medium | ~60 MB | [Télécharger](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium) |

### Exemple de téléchargement

```bash
# Créer le dossier
mkdir -p assets/models

# Télécharger la voix anglaise high quality
cd assets/models
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx.json

# Vérifier
ls -lh en_US-ljspeech-high.*
```

---

## 📥 Télécharger les Modèles ONNX

### Modèles requis

Après l'installation, télécharge les modèles ONNX pour les voix que tu souhaites utiliser.

#### 1. Voice TTS (Piper)

```bash
cd /home/server/aiserver
mkdir -p assets/models

# Voix anglaise (configurée par défaut) - High Quality
wget -O assets/models/en_US-ljspeech-high.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx

wget -O assets/models/en_US-ljspeech-high.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx.json

# Voix anglaise (alternative) - Low Quality (plus rapide)
wget -O assets/models/en_US-danny-low.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx

wget -O assets/models/en_US-danny-low.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx.json
```

#### 2. VAD (Silero)

```bash
# Télécharger le modèle VAD Silero
wget -O assets/models/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx
```

#### 3. Vérifier les modèles

```bash
ls -lh assets/models/
```

**Sortie attendue :**
```
-rw-r--r-- 1 user user 120M Mar 31 10:00 en_US-ljspeech-high.onnx
-rw-r--r-- 1 user user  2.5K Mar 31 10:00 en_US-ljspeech-high.onnx.json
-rw-r--r-- 1 user user  20M Mar 31 10:01 en_US-danny-low.onnx
-rw-r--r-- 1 user user  1.8K Mar 31 10:01 en_US-danny-low.onnx.json
-rw-r--r-- 1 user user  2.2M Mar 31 10:02 silero_vad.onnx
```

---

### Script de téléchargement automatique

Crée un script `download_models.sh` :

```bash
#!/bin/bash
# download_models.sh - Télécharge tous les modèles requis

set -e

MODEL_DIR="assets/models"
mkdir -p "$MODEL_DIR"

echo "📥 Téléchargement des modèles..."

# Piper TTS - English High
echo "🔊 en_US-ljspeech-high..."
wget -q --show-progress -O "$MODEL_DIR/en_US-ljspeech-high.onnx" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx
wget -q --show-progress -O "$MODEL_DIR/en_US-ljspeech-high.onnx.json" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ljspeech/high/en_US-ljspeech-high.onnx.json

# Piper TTS - English Low (backup)
echo "🔊 en_US-danny-low..."
wget -q --show-progress -O "$MODEL_DIR/en_US-danny-low.onnx" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx
wget -q --show-progress -O "$MODEL_DIR/en_US-danny-low.onnx.json" \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/danny/low/en_US-danny-low.onnx.json

# Silero VAD
echo "🎤 Silero VAD..."
wget -q --show-progress -O "$MODEL_DIR/silero_vad.onnx" \
  https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx

echo "✅ Tous les modèles sont téléchargés dans $MODEL_DIR"
ls -lh "$MODEL_DIR"
```

**Utilisation :**
```bash
chmod +x download_models.sh
./download_models.sh
```

---

## 📄 Licence

Ce projet est open-source. Voir le fichier de licence pour plus de détails.
