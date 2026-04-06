# Rapport Technique — aiserver

> Serveur vocal IA temps réel pour l'assistance à la livraison  
> Plateforme : NVIDIA Jetson Orin Nano 8 Go  
> Date : Avril 2026

---

## Section 1 — Technologies

### 1.1 Technologies existantes considérées

Plusieurs technologies ont été examinées avant de constituer la pile logicielle finale du serveur aiserver :

| Domaine | Technologies considérées |
|---|---|
| **Speech-to-Text (STT)** | OpenAI Whisper (PyTorch), faster-whisper (CTranslate2), Google Cloud Speech-to-Text, Vosk |
| **Débruitage audio** | RNNoise (pyrnnoise), DeepFilterNet, NoiseTorch |
| **LLM** | Ollama (local), OpenAI API (cloud), DSPy, LiteLLM |
| **Text-to-Speech (TTS)** | Piper TTS, Kokoro-82M, Coqui TTS, Edge TTS, Google Cloud TTS |
| **Voice Activity Detection** | Silero VAD (ONNX), WebRTC VAD, RNNoise VAD |
| **Communication temps réel** | WebRTC (aiortc), WebSocket pur, gRPC streaming |
| **Framework web** | FastAPI + Uvicorn, Flask + Gunicorn, Django Channels |

**Critères de sélection :**
- **Embarquabilité** : le serveur doit fonctionner sur NVIDIA Jetson Orin Nano (8 Go de mémoire unifiée)
- **Latence faible** : pipeline temps réel pour conversation vocale naturelle
- **Autonomie** : fonctionnement 100 % local, sans dépendance cloud
- **Qualité** : précision STT, naturel du TTS, pertinence des réponses LLM

### 1.2 Technologies retenues et justification des choix

| Composant | Technologie retenue | Justification |
|---|---|---|
| **STT** | **faster-whisper** (modèle `small.en`, int8) | CTranslate2 offre un rapport vitesse/précision nettement supérieur à Whisper PyTorch sur GPU embarqué. Le mode `int8` réduit l'empreinte mémoire de ~40 % par rapport au `float16` |
| **Débruitage** | **DeepFilterNet2** | Modèle optimisé pour les appareils embarqués avec ~20 ms de latence. Nettement plus performant que RNNoise sur la suppression de bruit ambiant tout en préservant la parole |
| **LLM** | **Ollama** avec le modèle **smollm2:360m** | smollm2:360m est un modèle compact spécialement conçu pour l'inférence edge. Ollama fournit une API HTTP simple avec gestion du contexte et du streaming |
| **TTS** | **Piper TTS** (voix `en_US-hfc_female-medium`) + **Kokoro-82M** en alternative | Piper offre une qualité sonore élevée avec un modèle ONNX léger (~60 Mo). Kokoro-82M (int8) offre une alternative ultra-rapide optimisée CPU |
| **VAD** | **Silero VAD** (ONNX) | Modèle léger, précise et rapide. L'inférence ONNX fonctionne efficacement sur CPU/GPU avec un footprint mémoire minimal |
| **Communication** | **WebRTC** (aiortc) + **WebSocket** | WebRTC pour le transport audio temps réel (codec Opus, buffer jitter natif). WebSocket pour le signaling SDP/ICE et les événements textuels |
| **Framework** | **FastAPI** + **Uvicorn** | Framework async natif, performances élevées, documentation automatique OpenAPI |
| **Intent Detection** | **Sentence Transformers** (`paraphrase-multilingual-MiniLM-L12-v2`) + CSV d'exemples | Embeddings cosine similarity pour une détection d'intention rapide et sans LLM |

### 1.3 Avantages et inconvénients de ces choix

**Avantages :**
- **100 % local** : aucune donnée ne quitte le Jetson, conformité RGPD naturelle
- **Latence maîtrisée** : pipeline optimisé avec warmup au démarrage, streaming TTS, et VAD en temps réel
- **Modularité** : chaque service est injecté par composition root (main.py), permettant de remplacer un composant sans toucher aux autres
- **Économique** : pas de coût d'API cloud, fonctionnement autonome
- **Multi-TTS** : deux moteurs TTS disponibles (Piper pour la qualité, Kokoro pour la vitesse)

**Inconvénients :**
- **Limité par le matériel** : le Jetson Orin Nano 8 Go impose des compromis sur la taille des modèles (smollm2:360m au lieu de modèles 7B+, Whisper small au lieu de large)
- **Mémoire unifiée** : le CPU et le GPU partagent la même RAM de 8 Go, créant une compétition pour les ressources entre VAD (GPU), Whisper (GPU), DeepFilterNet (GPU/TensorRT), et le LLM (CPU/GPU)
- **Monolingue STT** : Whisper configuré en `small.en` ne comprend que l'anglais
- **Pas de fallback cloud** : si Ollama ou un modèle ONNX est indisponible, le service correspondant échoue

---

## Section 2 — Architecture globale

### 2.1 Vue d'ensemble du pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Client (Navigateur)                          │
│                     WebRTC Audio + WebSocket                        │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     WebSocket Service (signaling)                   │
│              Gestion de sessions, routage de messages               │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      WebRTC Service (aiortc)                        │
│        RTCPeerConnection, TTSAudioTrack, réception audio            │
└────────┬──────────────────────────────┬─────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────┐          ┌──────────────────┐
│  VAD Service    │          │  Denoise Service │
│  (Silero ONNX)  │          │ (DeepFilterNet2) │
└────────┬────────┘          └────────┬─────────┘
         │                            │
         └────────────┬───────────────┘
                      ▼
            ┌──────────────────┐
            │  Whisper Service │
            │  (faster-whisper)│
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │  Intent Service  │
            │ (Sentence-Transf.)│
            └────────┬─────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌───────────────┐       ┌──────────────────┐
│ Action Service│       │  Agent Service   │
│ (Intents      │       │  (Orchestrateur  │
│  connus)      │       │   STT→LLM→TTS)   │
└───────┬───────┘       └────────┬─────────┘
        │                        │
        │               ┌────────┴────────┐
        │               │                 │
        │               ▼                 ▼
        │       ┌───────────┐    ┌────────────────┐
        │       │ Piper TTS │    │ Kokoro TTS     │
        │       │ (quality) │    │ (fast/light)   │
        │       └───────────┘    └────────────────┘
        │               │                 │
        └───────────────┼─────────────────┘
                        ▼
              ┌──────────────────┐
              │ Delivery State   │
              │ Machine (MODE_1) │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Notification Svc │
              │ (Push au client) │
              └──────────────────┘
```

**Flux principal :**
1. Le client mobile envoie de l'audio via **WebRTC** (codec Opus, 48 kHz)
2. Le serveur décode l'audio en PCM float32 mono, le resample à 16 kHz
3. Le **VAD** (Silero) détecte les segments de parole en temps réel (chunks de 32 ms)
4. En fin d'utterance, l'audio est optionnellement débruité par **DeepFilterNet2**
5. **Whisper** transcrit l'audio en texte
6. Le **Intent Service** classe l'intention via des embeddings
7. Si l'intent est connu → **Action Service** exécute localement (sans LLM)
8. Sinon → **Ollama** génère une réponse (streaming)
9. La réponse est synthétisée par **Piper TTS** ou **Kokoro TTS**
10. L'audio TTS est streamé au client via **TTSAudioTrack** (aiortc)

### 2.2 STT (Speech-to-Text)

Le service STT repose sur **faster-whisper**, une implémentation optimisée de Whisper utilisant CTranslate2.

- **Mode** : `embedded` (chargé dans le même process Python)
- **Backend** : `faster-whisper` (CTranslate2)
- **Modèle** : `small.en` (~460 Mo)
- **Device** : `cuda` (GPU Jetson)
- **Compute type** : `int8` (quantifié)
- **Beam size** : 1 (compromis vitesse/précision)
- **Langue** : `en` (anglais forcé)

Le service expose deux API :
- `transcribe(wav_bytes)` : pour compatibilité legacy (entrée WAV)
- `transcribe_pcm(samples, sample_rate)` : API recommandée pour le pipeline WebRTC (entrée NumPy float32)

Après transcription, un **garbage collection CUDA** (`torch.cuda.empty_cache()`) est effectué pour éviter l'OOM sur le Jetson.

### 2.3 Débruitage audio (DeepFilterNet)

Le débruitage utilise **DeepFilterNet2**, un modèle optimisé pour les appareils embarqués avec une latence cible de ~20 ms.

- **Backend** : `deepfilternet` (via la librairie `deepfilternet` Python)
- **Modèle** : DeepFilterNet2 (par défaut via `df.init_df(default_model='DeepFilterNet2')`)
- **Fréquence native** : 48 kHz (le modèle effectue automatiquement le resampling 16k → 48k → 16k via `scipy.signal.resample_poly`)
- **Inférence** : `torch.inference_mode()` avec tenseurs PyTorch

**Deux modes de fonctionnement :**
1. **Utterance-level** (défaut) : le débruitage est appliqué sur l'utterance complète après détection VAD, avant l'envoi à Whisper. Ce mode est configuré via `DENOISE_FOR_STT=true`.
2. **Streaming** (optionnel) : débruitage chunk par chunk avant le VAD via `DENOISE_BEFORE_VAD=true`. Plus propre mais ajoute une latence perceptible sur la détection de parole.

Par défaut, les deux sont **désactivés** (`DENOISE_ENABLED=false`) pour privilégier la latence.

### 2.4 Intent Solver

Le système de détection d'intentions fonctionne par **similarité cosinus d'embeddings** :

- **Modèle d'embedding** : `paraphrase-multilingual-MiniLM-L12-v2` (Sentence Transformers)
- **Device** : `cpu` (forcé pour économiser la VRAM du Jetson)
- **Seuil de similarité** : `0.60` (cosine similarity)
- **Données d'entraînement** : fichier CSV (`intent_detection/intentions.csv`) contenant ~700 exemples répartis sur 8 intentions :
  - `start_navigation`
  - `show_deliveries`
  - `get_next_client_name`
  - `get_next_delivery_address`
  - `get_possible_delivery_failure_reason`
  - `get_package_info`
  - `show_map`
  - `INCONNU` (intention non reconnue)

**Fonctionnement :**
1. Le texte transcrit est comparé à tous les exemples du CSV via embeddings
2. L'intention dont l'exemple le plus proche dépasse le seuil est retournée
3. Si `INTENT_GATE_LLM=true`, le LLM n'est pas appelé pour les intents connus (économie de ressources)
4. L'**Action Service** peut exécuter localement les intents connus sans passer par le LLM (`ACTION_SKIP_LLM_FOR_KNOWN_INTENTS=true`)

### 2.5 LLM (Ollama)

Le LLM est servi par **Ollama**, exécuté en tant que service externe sur `localhost:11434`.

- **Modèle** : `smollm2:360m` (~360 millions de paramètres)
- **Contexte** : 1024 tokens (`OLLAMA_CONTEXT_WINDOW`)
- **Max tokens de sortie** : 50 (`OLLAMA_NUM_PREDICT`)
- **Température** : 0.7
- **Top-k** : 20, **Top-p** : 0.95
- **Pénalité de répétition** : 1.4
- **Stop tokens** : `</s>`, `<|endoftext|>`
- **Mode "thinking"** : désactivé (`OLLAMA_THINK=false`)

**System prompt** (fichier `system_prompt.md`) :
> *"You are Rytle, a friendly but quiet AI assistant. Stay calm, kind, and very brief—no long explanations or extra text. Always answer as Rytle, using only 1–2 short sentences."*

Le service supporte le **streaming** : les tokens sont yieldés au fur et à mesure pour alimenter le TTS en temps réel, réduisant la latence perçue.

### 2.6 TTS (Text-to-Speech)

Deux moteurs TTS sont disponibles :

**Piper TTS (principal) :**
- **Modèle** : `en_US-hfc_female-medium.onnx` (~60 Mo)
- **Qualité** : Medium-High
- **Sample rate natif** : 22 050 Hz
- **Upsampling** : soxr vers 48 kHz (WebRTC/Opus)
- **Fallbacks de resampling** : scipy → librosa → numpy interpolation

**Kokoro-82M (alternative) :**
- **Modèle** : `kokoro-v1.0.int8.onnx` (~800 Mo, quantifié int8)
- **Voix** : `af_sarah` (US female)
- **Sample rate natif** : 24 000 Hz
- **Optimisé CPU** : ONNX Runtime, très rapide sur Jetson

**Streaming TTS :**
Le TTS fonctionne en mode streaming : le texte est segmenté en phrases complètes (délimitées par `.`, `!`, `?`, `,`) avant synthèse. Chaque segment est synthétisé indépendamment puis envoyé au client avec :
- Un **crossfade** de 100 ms entre segments (`TTS_SEGMENT_OVERLAP_MS`)
- Un **buffer de prélecture** de 1 500 ms avant de commencer la lecture
- Un **scheduler** envoyant des frames de 10 ms au TTSAudioTrack

---

## Section 3 — Configuration des modules

### 3.1 STT — fréquence d'entrée, modèle, compute type, paramètres

| Paramètre | Valeur | Description |
|---|---|---|
| `WHISPER_MODE` | `embedded` | Modèle chargé dans le process Python |
| `WHISPER_BACKEND` | `faster-whisper` | CTranslate2 (plus rapide que PyTorch) |
| `WHISPER_MODEL` | `small.en` | Modèle anglais, ~460 Mo |
| `WHISPER_DEVICE` | `cuda` | Inférence sur GPU Jetson |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantification 8 bits (réduction mémoire ~40 %) |
| `WHISPER_BEAM_SIZE` | `1` | Beam search size (1 = greedy, plus rapide) |
| `WHISPER_LANGUAGE` | `en` | Langue forcée (pas d'auto-détection) |
| Fréquence d'entrée | **16 kHz** mono float32 | Resampling automatique si nécessaire |

### 3.2 Débruitage — mode, backend, seuils, streaming vs utterance-level

| Paramètre | Valeur | Description |
|---|---|---|
| `DENOISE_ENABLED` | `false` (défaut) | Activation globale du débruitage |
| `DENOISE_BACKEND` | `deepfilternet` | Backend utilisé |
| `DENOISE_BEFORE_VAD` | `false` | Débruitage streaming avant VAD (désactivé par défaut pour la latence) |
| `DENOISE_FOR_STT` | `false` | Débruitage utterance-level avant STT |
| Modèle | DeepFilterNet2 | Optimisé embarqué, ~20 ms de latence |
| Fréquence interne | 48 kHz | Resampling automatique 16k ↔ 48k via `scipy.signal.resample_poly` |
| Inférence | `torch.inference_mode()` | Mode inférence PyTorch (pas de gradient) |

**Streaming vs Utterance-level :**
- **Utterance-level** (recommandé) : le VAD fonctionne sur l'audio brut, seul l'output final est débruité avant STT. Latence minimale.
- **Streaming** : chaque chunk de 32 ms est débruité avant le VAD. Qualité audio supérieure mais latence accrue et charge GPU plus élevée.

### 3.3 Intent Solver — fonctionnement, fichier CSV, seuil de similarité, modèle d'embedding

| Paramètre | Valeur | Description |
|---|---|---|
| `INTENT_CSV_PATH` | `intent_detection/intentions.csv` | Fichier d'exemples d'entraînement |
| `INTENT_EMBED_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Modèle d'embedding (118M params) |
| `INTENT_DEVICE` | `cpu` | Forcé sur CPU pour économiser la VRAM |
| `INTENT_THRESHOLD` | `0.60` | Seuil de similarité cosinus minimum |
| `INTENT_GATE_LLM` | `false` | Si `true`, bypass du LLM pour intents connus |
| `INTENT_EMBED_DOWNLOAD_ON_STARTUP` | `false` | Téléchargement du modèle au démarrage |

**Fonctionnement détaillé :**
1. Au démarrage, le modèle Sentence Transformers est chargé et les exemples du CSV sont encodés en embeddings
2. À chaque transcription, le texte est encodé et comparé (cosine similarity) à tous les exemples
3. L'intent dont le score dépasse `0.60` est retourné, sinon `INCONNU`
4. Si un intent connu est détecté et `ACTION_SKIP_LLM_FOR_KNOWN_INTENTS=true`, l'Action Service exécute l'action localement sans appeler le LLM

**Intentions connues (8) :**
`start_navigation`, `show_deliveries`, `get_next_client_name`, `get_next_delivery_address`, `get_possible_delivery_failure_reason`, `get_package_info`, `show_map`, `INCONNU`

### 3.4 TTS — modèle Piper/Kokoro, voix, vitesse, calibrage, sample rate

**Piper TTS :**

| Paramètre | Valeur |
|---|---|
| `PIPER_MODEL_PATH` | `assets/models/en_US-hfc_female-medium.onnx` |
| `PIPER_CONFIG_PATH` | `assets/models/en_US-hfc_female-medium.onnx.json` |
| Voix | hfc_female (US female, medium quality) |
| Sample rate natif | 22 050 Hz |
| Sample rate output | 48 000 Hz (upsampling soxr) |

**Kokoro TTS :**

| Paramètre | Valeur |
|---|---|
| `KOKORO_MODEL_PATH` | `assets/models/kokoro-v1.0.int8.onnx` |
| `KOKORO_VOICES_PATH` | `assets/models/voices-v1.0.bin` |
| `KOKORO_VOICE` | `af_sarah` (US female) |
| `KOKORO_LANGUAGE` | `en-us` |
| `KOKORO_SPEED` | `1.0` (normale) |
| Sample rate natif | 24 000 Hz |
| Sample rate output | 48 000 Hz (upsampling soxr) |

**Paramètres communs de calibrage :**

| Paramètre | Valeur | Description |
|---|---|---|
| `TTS_STREAM_WORD_CHUNK_SIZE` | `8` | Nombre de mots avant de déclencher la synthèse |
| `TTS_SEGMENT_OVERLAP_MS` | `100` | Fondu entre segments pour éviter les coupures |
| `TTS_SEGMENT_QUEUE_MAXSIZE` | `5` | Taille max du buffer de segments TTS |
| `TTS_PLAYBACK_PREBUFFER_MS` | `1500` | Buffer avant démarrage de la lecture |
| `TTS_BUFFER_LOW_WATERMARK_MS` | `1200` | Déclenche la synthèse du segment suivant |
| `TTS_FRAME_INTERVAL_MS` | `10` | Intervalle entre frames WebRTC |
| `TTS_TRIM_SILENCE_THRESHOLD` | `0.0001` | Seuil de détection du silence |
| `TTS_TRIM_SILENCE_PAD_MS` | `80` | Padding avant coupure silence |
| `TTS_TRIM_TRAILING` | `false` | Désactivé pour éviter de couper les fins de phrases |

---

## Section 4 — Traitement de la voix

### 4.1 Chemin complet d'un signal audio (entrée → sortie)

```
Client mobile (navigateur)
    │
    ├─► Encodage Opus (48 kHz)
    │
    ▼
WebRTC (aiortc) — RTCPeerConnection
    │
    ├─► Réception av.AudioFrame (PyAV)
    │
    ▼
AudioService.av_frame_to_array()
    │
    ├─► Resampler PyAV : format s16, mono, target_rate
    │   (si le frame natif est à 48 kHz → conversion directe)
    │
    ▼
Signal PCM float32 mono @ 48 kHz
    │
    ├─► Resampling haute qualité (soxr) 48k → 16k
    │   pour VAD et STT
    │
    ▼
Signal PCM float32 mono @ 16 kHz
    │
    ├─► [Optionnel] DeepFilterNet2 (si DENOISE_BEFORE_VAD=true)
    │   Resampling 16k→48k→denoise→48k→16k
    │
    ▼
VAD Service (Silero VAD)
    │
    ├─► Chunks de 32 ms
    │   Détection speech/silence (hystérésis)
    │   Bufferisation de l'utterance
    │
    ▼
Fin d'utterance détectée (VADResult.type = "utterance_end")
    │
    ├─► [Optionnel] DeepFilterNet2 utterance-level (si DENOISE_FOR_STT=true)
    │
    ├─► Normalisation (peak à 0.95)
    │
    ▼
Whisper Service (faster-whisper, small.en, int8, CUDA)
    │
    ├─► Resampling 16k → 16k (si nécessaire)
    │   Transcription → texte
    │   Garbage collection CUDA
    │
    ▼
Intent Service (Sentence Transformers, CPU)
    │
    ├─► Embedding → cosine similarity → intent
    │
    ├─► Si intent connu → Action Service (exécution locale)
    │   └─► Réponse → Piper TTS → Audio TTS
    │
    └─► Si intent inconnu → Ollama LLM (streaming)
        └─► Tokens → Piper TTS (streaming) → Audio TTS
            │
            ▼
AudioService.array_to_av_frames_direct()
    │
    ├─► Découpage en frames de 20 ms (960 samples @ 48k)
    │   Format s16, mono
    │
    ▼
TTSAudioTrack._queue.put(frame)
    │
    ├─► aiortc envoie les frames via WebRTC
    │
    ▼
Client mobile — décodage Opus → haut-parleur
```

### 4.2 Étapes de traitement : sampling, resampling, compression, débruitage, VAD

**Échantillonnage initial :**
- Le client WebRTC encode en **Opus à 48 kHz** (standard WebRTC/Opus)
- Le serveur reçoit des `av.AudioFrame` via aiortc
- PyAV resample en **s16 mono** via `av.AudioResampler`
- Conversion en PCM float32 normalisé [-1, 1]

**Resampling :**
- **48k → 16k** : pour VAD et STT (Whisper attend 16 kHz). Utilise `soxr.resample()` (qualité professionnelle) avec fallbacks scipy → librosa → numpy
- **16k → 48k** : pour le TTS (Piper produit du 22 050 Hz, Kokoro du 24 000 Hz, tous deux upsampled à 48 kHz pour WebRTC)

**Compression / Normalisation :**
- `AudioService.normalize()` : peak normalization à 0.95 pour éviter le clipping et améliorer la reconnaissance Whisper sur les segments faibles
- Le TTS applique un **fade-out exponentiel** (`exp(-6.0)`) sur les derniers échantillons pour des transitions douces

**Débruitage :**
- DeepFilterNet2 fonctionne nativement à 48 kHz
- Pipeline : `resample_poly(16k→48k)` → `torch.inference_mode(enhance())` → `resample_poly(48k→16k)`
- Le tenseur d'entrée est de shape `[1, T]` (batch de 1, T échantillons)

**VAD :**
- Silero VAD ONNX : chunks de **32 ms** (512 samples @ 16 kHz)
- Modèle RNN avec état récurrent (h, c) de shape `[2, 1, 64]` conservé entre les chunks
- **Hystérésis** : seuil de démarrage à `0.85`, seuil de continuation à `0.50`
- **Pre-roll** : 400 ms d'audio conservés avant le `speech_start` pour ne pas couper le début des mots
- **Post-roll** : 300 ms après la fin détectée pour capturer les fins de syllabes
- **Garde-fou** : `VAD_MAX_UTTERANCE_MS = 6000` force une fin d'utterance après 6 secondes

### 4.3 Gestion des interruptions (barge-in)

Le système d'interruption permet à l'utilisateur de couper la parole de l'IA :

**Déclenchement :**
1. Le VAD détecte un `speech_start` pendant que `session.tts_playing = true` ou `session.processing_lock.locked()`
2. `agent.on_user_speech_start()` est appelé
3. Calcul du temps écoulé depuis le début du TTS ou du processing : `elapsed_ms`

**Blocage en MODE_1 :**
- Si la machine à états de livraison est active (`MODE_1`), les interruptions sont **ignorées** pour les questions critiques (état de livraison, raison d'échec)
- Les TTS marqués `tts_interruptible = false` ne sont pas interruptibles

**Décision d'interruption :**
```
Si elapsed_ms < 1000 ms :
    └─► Mot d'interruption ("no", "stop", "wait"...) → "interruption"
    └─► Mot de continuation ("also", "and", "plus"...) → "continuation"
    └─► Défaut → "continuation"
Sinon (elapsed_ms >= 1000 ms) :
    └─► Mot de continuation → "continuation"
    └─► Défaut → "interruption"
```

**Actions d'interruption :**
1. `session.cancel_flag = true` → annule le pipeline en cours
2. `session.tts_track.clear()` → vide la queue audio TTS
3. Envoi de `{"type": "tts_stop_now"}` au client via WebSocket
4. En mode **continuation** : le nouveau texte est fusionné avec le message utilisateur actif
5. En mode **interruption** : le message actif est supprimé, nouveau tour de conversation

**Événements WebSocket :**
| Type | Direction | Description |
|---|---|---|
| `vad: speech_start` | Serveur → Client | Détection de début de parole |
| `interruption_decision` | Serveur → Client | Décision avec `elapsed_ms` |
| `tts_stop_now` | Serveur → Client | Arrêt immédiat du TTS |
| `interrupted` | Serveur → Client | Notification d'interruption |

---

## Section 5 — Communication réseau

### 5.1 WebRTC — rôle, flux audio, peer management

**Rôle :** WebRTC est le protocole de transport audio temps réel entre le client mobile et le serveur. Il gère :
- L'encodage/décodage **Opus** (codec audio optimisé pour la voix)
- La gestion de la **gigue réseau** (jitter buffer natif du navigateur)
- La **NAT traversal** via STUN/TURN
- Le transport de frames audio dans les deux directions

**Implémentation côté serveur (aiortc) :**

Le `WebRTCService` gère un `RTCPeerConnection` par session :

1. **Création du peer** : `WebRTCService.create_peer(session)` crée un `RTCPeerConnection` avec la configuration ICE (serveur STUN : `stun:stun.l.google.com:19302`)
2. **TTSAudioTrack** : une `MediaStreamTrack` personnalisée est créée et ajoutée au peer (`pc.addTrack(tts_track)`). Cette track contient une queue asyncio (`_queue`) qui stocke les frames audio TTS
3. **Négociation SDP** : le client envoie une offre SDP via WebSocket, le serveur répond avec une réponse SDP (`handle_offer`)
4. **Candidats ICE** : échangés via WebSocket pour établir la connexion directe

**Réception audio :**
- La méthode `_process_audio_track()` est une boucle infinie qui reçoit les frames via `track.recv()`
- Chaque frame est décodée en PCM float32, resamplée à 16 kHz, puis passée au VAD
- En cas de détection de fin d'utterance, l'audio est envoyé à l'AgentService

**Envoi audio (TTS) :**
- Le TTS produit du PCM float32 @ 48 kHz
- `AudioService.array_to_av_frames_direct()` découpe en frames de **20 ms** (960 samples @ 48 kHz)
- Chaque frame est convertie en `av.AudioFrame` (format s16, mono, PTS calculé)
- Les frames sont empilées dans `TTSAudioTrack._queue`
- La méthode `TTSAudioTrack.recv()` est appelée par aiortc ~50 fois/seconde pour envoyer les frames au client

### 5.2 WebSocket — rôle, sessions, signaling

**Rôle :** Le WebSocket sert de canal de **signaling** et de transmission d'événements textuels :

1. **Signaling WebRTC** :
   - `{"type": "offer", "sdp": "..."}` → le client envoie son offre SDP
   - `{"type": "answer", "sdp": "..."}` → le serveur répond avec sa réponse SDP
   - `{"type": "ice", "candidate": {...}}` → échange de candidats ICE
   - `{"type": "start"}` / `{"type": "stop"}` → contrôle de session

2. **Événements serveur → client** :
   - `{"type": "transcript", "text": "..."}` → texte STT
   - `{"type": "response", "text": "..."}` → fragment de réponse LLM
   - `{"type": "intent", "intent": "..."}` → intention détectée
   - `{"type": "emotion", "name": "speaking"}` → émotion de l'IA
   - `{"type": "ask_photo_event", ...}` → demande de photo (delivery flow)
   - `{"type": "vad", "event": "speech_start"}` → événements VAD
   - `{"type": "interruption_decision", ...}` → décision d'interruption

3. **Événements client → serveur** :
   - `{"type": "test_tts", "text": "..."}` → test TTS
   - `{"type": "arrived", "id": "trip_id"}` → notification d'arrivée (delivery)
   - `{"type": "photo_taken"}` / `{"type": "photo_not_taken"}` → réponse à la demande de photo
   - `{"type": "external_control", "action": "...", "extras": {...}}` → contrôle externe

**Gestion des sessions :**
- Chaque connexion WebSocket crée une `Session` avec un `client_id` UUID4 unique
- Les sessions sont enregistrées dans `WebSocketService._sessions: dict[str, Session]`
- Un **ping keep-alive** natif WebSocket est envoyé toutes les 10 secondes
- À la déconnexion, `disconnect(session)` nettoie : annulation du ping, suppression du registre, cleanup WebRTC

### 5.3 Interactions entre les deux protocoles (qui fait quoi et quand)

```
┌─────────────────────────────────────────────────────────────────┐
│ Connexion initiale                                               │
│                                                                  │
│ 1. Client → WebSocket : connexion ws://server/ws                │
│ 2. Serveur → WebSocketService : create_session(client_id=UUID4) │
│ 3. Serveur → Client : WebSocket accepté                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Établissement WebRTC                                             │
│                                                                  │
│ 4. Client → WebSocket : {"type": "offer", "sdp": "..."}         │
│ 5. Serveur → WebRTCService : handle_offer(session, sdp)         │
│    ├── create_peer(session) → RTCPeerConnection + TTSAudioTrack │
│    ├── setRemoteDescription(offer)                               │
│    ├── createAnswer()                                            │
│    └── setLocalDescription(answer)                               │
│ 6. Serveur → WebSocket : {"type": "answer", "sdp": "..."}       │
│ 7. Client ↔ Serveur : échange de candidats ICE via WebSocket    │
│ 8. Connexion WebRTC établie (flux audio bidirectionnel)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Flux audio continu                                               │
│                                                                  │
│ Client → Serveur (WebRTC) :                                     │
│   - Frames audio Opus encodées (48 kHz)                          │
│   - Décodées par aiortc → av.AudioFrame                          │
│   - Traitement : resample → VAD → STT → LLM → TTS              │
│                                                                  │
│ Serveur → Client (WebRTC) :                                     │
│   - Frames audio TTS via TTSAudioTrack (48 kHz, 20 ms)           │
│   - Décodées par le navigateur → haut-parleur                    │
│                                                                  │
│ Serveur → Client (WebSocket) : événements textuels               │
│   - transcript, response, intent, emotion, vad, etc.            │
│                                                                  │
│ Client → Serveur (WebSocket) : contrôle                          │
│   - arrived, photo_taken, test_tts, external_control             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Déconnexion                                                      │
│                                                                  │
│ 9. Client ferme WebSocket ou WebRTC                              │
│ 10. Serveur → WebSocketService : disconnect(session)             │
│     ├── Annulation du ping keep-alive                            │
│     ├── webrtc.cleanup(session) → close peer, stop tts_track     │
│     └── Suppression du registre de sessions                      │
└─────────────────────────────────────────────────────────────────┘
```

**Résumé de la répartition :**

| Protocole | Rôle | Contenu |
|---|---|---|
| **WebRTC** | Transport audio temps réel | Frames audio Opus encodées (client → serveur) et TTS (serveur → client) |
| **WebSocket** | Signaling + événements | SDP offer/answer, candidats ICE, transcripts, réponses LLM, intents, émotions, contrôle |

---

## Section 6 — Machine à états du serveur

### 6.1 Description et objectif

La **DeliveryStateMachine** est une machine à états qui gère un flux conversationnel structuré pour la **complétion de livraison**. Elle est utilisée lorsqu'un livreur arrive à destination et doit confirmer l'état de sa livraison.

**Objectif :** Remplacer le LLM par un flux déterministe pour les questions critiques de livraison, garantissant :
- Une collecte fiable de l'état de livraison (complétée ou échouée)
- En cas d'échec, la collecte d'une raison (parmi une liste prédéfinie)
- L'annonce automatique de la prochaine livraison
- Le démarrage automatique de la navigation vers la prochaine adresse

### 6.2 Schéma des états (MODE_0 / MODE_1)

Le serveur fonctionne selon **deux modes** :

**MODE_0 — Flux normal :**
```
STT → Intent Detection → Action Service (si intent connu)
                      → LLM + TTS (si intent inconnu)
```

**MODE_1 — Flux de complétion de livraison :**
```
┌──────────────────────────────────────────────────────────────┐
│                      MODE_1                                   │
│                                                               │
│  ┌──────────┐     YES         ┌──────────┐                   │
│  │ STATE_1  │ ───────────►   │ STATE_4  │                   │
│  │ ASK_     │                 │ COMPLETE │                   │
│  │ COMPLETION│                │ (update   │                   │
│  │          │                 │  trip)    │                   │
│  │ "Livraison│                └────┬─────┘                   │
│  │  terminée│        NO            │                         │
│  │  ?"      │ ───────────► ┌───────▼──────┐                  │
│  └──────────┘              │  STATE_2     │                  │
│       │                    │  ASK_REASON  │                  │
│       │ retry (invalide)   │ "Pourquoi ?" │                  │
│       └───────────────────►│              │                  │
│                            │ ┌──────────┐ │                  │
│                            │ │ STATE_6  │ │                  │
│                            │ │ ASK_PHOTO│ │ (raison 1 only)  │
│                            │ │ "Photo ?"│ │                  │
│                            │ └────┬─────┘ │                  │
│                            └──────┼───────┘                  │
│                                   │                          │
│                                   ▼                          │
│                            ┌──────────┐                      │
│                            │ STATE_5  │                      │
│                            │ EXIT     │                      │
│                            │ → MODE_0 │                      │
│                            └──────────┘                      │
└──────────────────────────────────────────────────────────────┘
```

**États détaillés :**

| État | Nom | Rôle | TTS émis |
|---|---|---|---|
| `STATE_0` | Normal | MODE_0, pipeline STT→LLM→TTS standard | — |
| `STATE_1` | ASK_COMPLETION | Demande si la livraison est terminée | *"you have arrived at the destination. may I ask if the delivery is completed?"* |
| `STATE_2` | ASK_REASON | Demande la raison de l'échec | *"Can you give me a reason ? You can say 'list' to hear the options or ask for it."* |
| `STATE_4` | COMPLETE | Mise à jour du statut du trip | — |
| `STATE_5` | EXIT | Retour au MODE_0 | Annonce de la prochaine livraison |
| `STATE_6` | ASK_PHOTO | Demande de photo (raison 1 = client indisponible) | *"Can you please take a photo of the package?"* |

### 6.3 Conditions de transition

**Entrée en MODE_1 :**
- Déclenchée par l'Action Service lorsqu'un trip est identifié et que le livreur est arrivé à destination
- `enter_mode_1(session, trip_id)` positionne `STATE_1` automatiquement

**Transitions STATE_1 :**
| Input utilisateur | Transition | Action |
|---|---|---|
| Mot YES (`yes`, `yep`, `yeah`) | STATE_1 → STATE_4 → STATE_5 | `update_trip(status="COMPLETED")` + annonce prochaine livraison + démarrage navigation |
| Mot NO (`no`, `nope`) | STATE_1 → STATE_2 | TTS : demande de raison |
| Input invalide | STATE_1 → STATE_1 (retry) | TTS : *"Sorry, I didn't understand. Could you repeat?"* |

**Transitions STATE_2 :**
| Input utilisateur | Transition | Action |
|---|---|---|
| Intent `get_possible_delivery_failure_reason` ou mot `list` | STATE_2 → STATE_2 | Énumération des raisons d'échec |
| Numéro valide (1-6) ≠ 1 | STATE_2 → STATE_4 → STATE_5 | `update_trip(status="FAILED", reason=N)` + annonce prochaine livraison |
| Numéro = 1 (Client indisponible) | STATE_2 → STATE_6 | Envoi `ask_photo_event` au client + TTS demande photo |
| Numéro invalide | STATE_2 → STATE_2 (retry) | TTS : demande un numéro valide |
| Pas de numéro détecté | STATE_2 → STATE_2 (retry) | TTS : *"Sorry, I didn't understand..."* |

**Transitions STATE_6 :**
| Événement | Transition | Action |
|---|---|---|
| `photo_taken` (via WebSocket) | STATE_6 → STATE_4 → STATE_5 | `update_trip(status="FAILED", reason="Customer not available")` + annonce |
| `photo_not_taken` (via WebSocket) | STATE_6 → STATE_4 → STATE_5 | Même action sans photo |
| Transcript STT | STATE_6 → STATE_6 (ignoré) | Aucun TTS, on attend l'événement photo |

**Transitions STATE_5 :**
| Input | Transition |
|---|---|
| Tout input | STATE_5 → STATE_0 (`exit_to_mode_0`, reset du contexte) |

**Sortie de MODE_1 :**
- Automatique après STATE_5 : le contexte est réinitialisé (`ctx.reset()`) et le serveur revient en MODE_0
- Le contexte est aussi réinitialisé si un `arrived` est reçu pendant qu'un flow précédent est encore actif

### 6.4 Cas particuliers et gestion des erreurs

**Ignorer les inputs pendant le TTS en MODE_1 :**
- Si le TTS est en train de parler (`session.tts_playing = true`) et que la machine est en MODE_1, les inputs utilisateur sont **ignorés**. Cela évite qu'une réponse tardive du VAD soit interprétée comme une commande.

**TTS non interruptibles en MODE_1 :**
- Les questions critiques (`STATE_1`, `STATE_2`) et les demandes de répétition sont marquées `interruptible = false`. L'utilisateur ne peut pas couper la parole pendant ces annonces.

**Annonce automatique de la prochaine livraison :**
- Après STATE_1 (YES) ou STATE_2 (raison sélectionnée), le serveur :
  1. Récupère les infos du prochain trip via le PlanningService
  2. Annonce la prochaine adresse et le nom du client
  3. Indique si c'est la dernière livraison
  4. Démarre automatiquement la navigation après 3 secondes (`_trigger_start_navigation_delayed`)

**Gestion des événements photo :**
- En STATE_6, le serveur ignore les transcripts STT et attend les événements `photo_taken` ou `photo_not_taken` via WebSocket
- L'événement `ask_photo_event` est envoyé au client Android pour déclencher l'appareil photo

**Fallback en cas d'erreur :**
- Si une exception survient dans le traitement de la machine à états, le pipeline normal (MODE_0) prend le relais
- Le contexte est conservé jusqu'à la fin de l'action `update_trip`, puis réinitialisé

**Pending arrived :**
- Si un événement `arrived` est reçu pendant qu'un flow MODE_1 est encore actif, le `trip_id` est stocké dans `session.pending_arrived_trip_id`
- Après le reset de MODE_1, ce pending est consommé automatiquement pour enchaîner le prochain flow

---

## Section 7 — Limites actuelles du serveur

### 7.1 Limites matérielles (Jetson, mémoire unifiée)

**NVIDIA Jetson Orin Nano 8 Go :**
- **CPU** : 6 cœurs ARM Cortex-A78AE
- **GPU** : 1024 cœurs NVIDIA Ampere avec 32 Tensor Cores
- **Performance IA** : jusqu'à 40 TOPS (selon source, jusqu'à 67 TOPS pour la version Super) [^1]
- **Mémoire** : 8 Go LPDDR5, **unifiée** entre CPU et GPU

**Contraintes liées à la mémoire unifiée :**
1. **Compétition CPU/GPU** : le CPU et le GPU partagent les mêmes 8 Go. Quand Whisper utilise le GPU (CUDA), il consomme de la RAM système. De même, quand le LLM tourne sur CPU, il réduit la mémoire disponible pour le GPU
2. **Taille des modèles limitée** :
   - Whisper `small.en` (~460 Mo) est le plus gros modèle STT viable. Le modèle `medium` (~1.5 Go) ou `large-v3` (>3 Go) risquerait l'OOM
   - smollm2:360m est un modèle très compact (360M params). Des modèles de 7B+ paramètres ne tiendraient pas en mémoire avec le reste du pipeline
   - DeepFilterNet2 + Silero VAD + Piper TTS consomment également de la VRAM via PyTorch/CUDA
3. **Risque d'OOM** : le garbage collection CUDA (`torch.cuda.empty_cache()`) est appelé après chaque transcription Whisper, mais des pics de mémoire peuvent survenir lors du chargement simultané de plusieurs modèles

**Performances :**
- La quantification `int8` de Whisper réduit l'empreinte mémoire mais dégrade légèrement la précision par rapport au `float16`
- Le LLM smollm2:360m, bien que rapide, a des capacités de raisonnement limitées comparé à des modèles plus grands

### 7.2 Limites logicielles (latence, modèles, concurrence)

**Latence :**
- **Première requête** : sans warmup, la première transcription STT peut prendre plusieurs secondes (chargement du modèle Whisper à la volée). Le préchauffage (`PREWARM_ON_STARTUP=true`) atténue ce problème mais augmente le temps de démarrage du serveur
- **Pipeline complet** : la latence totale (parole utilisateur → début TTS) est estimée entre 1.5 et 4 secondes selon la longueur de l'utterance et la complexité de la réponse LLM
  - STT (Whisper small.en int8) : ~200-800 ms
  - Intent detection : ~50-200 ms (CPU)
  - LLM (smollm2:360m, 50 tokens max) : ~500-2000 ms
  - TTS streaming : premier segment après ~300-600 ms de synthèse

**Modèles :**
- **Monolingue STT** : Whisper `small.en` ne comprend que l'anglais. Un déploiement multilingue nécessiterait un modèle `small` ou `medium` multilingue, plus lourd
- **Qualité TTS** : Piper medium est bon mais pas au niveau des TTS neuronaux cloud (Google, Azure). Kokoro, bien que rapide, a une qualité sonore inférieure
- **Capacités LLM** : smollm2:360m est limité en raisonnement complexe, compréhension contextuelle longue, et gestion des nuances

**Concurrence :**
- **Pipeline mono-thread par session** : `session.processing_lock` garantit qu'un seul pipeline STT→LLM→TTS s'exécute par session. Cela empêche les conflits mais limite le débit
- **Pas de limite explicite de sessions** : le serveur accepte autant de connexions WebSocket que possible, mais chaque session consomme de la mémoire (buffers audio, contexte conversationnel, état VAD)
- **Ollama mono-instance** : un seul serveur Ollama est utilisé. Plusieurs sessions simultanées créeraient une file d'attente sur le LLM

**Denoise :**
- DeepFilterNet2 en mode streaming (`DENOISE_BEFORE_VAD=true`) ajoute une latence perceptible sur la détection VAD. Par défaut, il est donc désactivé
- Le resampling 16k ↔ 48k pour DeepFilterNet (via scipy `resample_poly`) ajoute un overhead CPU

### 7.3 Pistes d'amélioration

**Performance / Latence :**
1. **Optimisation TensorRT** : le Jetson supporte TensorRT. Convertir les modèles ONNX (VAD, TTS, DeepFilterNet) en format TensorRT réduirait la latence d'inférence de 30-50 % [^2]
2. **Pipeline multi-sessions** : implémenter un pool de workers pour traiter plusieurs sessions en parallèle (limité par la mémoire disponible)
3. **Streaming STT** : utiliser le streaming de faster-whisper pour obtenir des résultats partiels avant la fin de l'utterance, réduisant la latence perçue
4. **Speculative decoding** : pour le LLM, utiliser un petit modèle pour générer rapidement puis vérifier avec un modèle plus grand

**Qualité :**
5. **STT multilingue** : passer à Whisper `medium` multilingue (si la mémoire le permet) ou utiliser un modèle plus petit comme `tiny` multilingue pour la détection de langue
6. **TTS de meilleure qualité** : intégrer VITS ou des modèles TTS neuronaux plus récents
7. **LLM plus capable** : passer à un modèle 1.5B-3B (ex: Qwen2.5-1.5B, Llama-3.2-1B) si la mémoire le permet après optimisation

**Robustesse :**
8. **Fallback cloud** : en cas d'indisponibilité d'Ollama ou d'un modèle ONNX, basculer vers une API cloud (OpenAI, Google)
9. **Health checks périodiques** : surveiller l'état des services externes (Ollama) et redémarrer automatiquement en cas de panne
10. **Rate limiting** : limiter le nombre de sessions simultanées pour éviter la saturation mémoire

**Fonctionnalités :**
11. **Conversation multi-tour avancée** : augmenter `MAX_HISTORY` et `OLLAMA_CONTEXT_WINDOW` pour des conversations plus riches
12. **Support de langues multiples** : ajouter des voix TTS françaises, espagnoles, etc. (Piper supporte de nombreuses langues)
13. **Enregistrement et analytics** : enregistrer les conversations pour analyse post-hoc (avec consentement utilisateur)
14. **Interface d'administration** : dashboard web pour monitorer les sessions, les performances, et les erreurs en temps réel

---

## Sources

[^1]: NVIDIA Jetson Orin Nano specifications — Accio.ai, StorageReview. Consulté en avril 2026.  
- https://www.accio.ai/find-product/jetson-orin-nano-specs  
- https://www.storagereview.com/review/nvidia-jetson-orin-nano-super-powering-deepseek-r1-70b-inference-at-the-edge

[^2]: NVIDIA TensorRT documentation — Optimisation d'inférence pour Jetson.  
- https://developer.nvidia.com/tensorrt

[^3]: faster-whisper GitHub repository — CTranslate2 implementation.  
- https://github.com/SYSTRAN/faster-whisper

[^4]: DeepFilterNet — Deep Learning Based Audio Denoising.  
- https://github.com/Rikorose/DeepFilterNet

[^5]: Silero VAD — Pre-trained enterprise-grade VAD models.  
- https://github.com/snakers4/silero-vad

[^6]: Piper TTS — Fast, local neural text to speech.  
- https://github.com/rhasspy/piper

[^7]: Kokoro TTS — High quality TTS model (82M parameters).  
- https://github.com/hexgrad/kokoro

[^8]: Ollama — Run large language models locally.  
- https://ollama.com/

[^9]: aiortc — WebRTC and ORTC implementation for Python.  
- https://aiortc.readthedocs.io/

[^10]: Sentence Transformers — Multilingual text embeddings.  
- https://www.sbert.net/
