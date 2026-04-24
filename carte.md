# Cartographie du projet `agent-nvidia-v2`

> Agent vocal embarqué (NVIDIA Jetson) pour livreurs, basé sur FastAPI + WebSocket.
> Pipeline complet : **Micro → VAD → STT → LLM → TTS → Client Android**

---

## Vue d'ensemble

```
Client Android (WebSocket ws://)
        │
        ├── Audio PCM binaire  ──────────────────────────────────────┐
        │                                                            ▼
        └── JSON (start/stop/arrived/photo_taken/external_control)  WebSocketAudioService
                                                                      │
                                          ┌───────────────────────────┤
                                          │                           │
                                        VADService             AgentService
                                       (Silero ONNX)          ┌─────┴──────┐
                                          │                    │            │
                                   speech_end             WhisperService  OllamaService
                                          │               (faster-whisper) (Ollama HTTP)
                                          │                    │            │
                                          └────────────────────┤            │
                                                               ▼            │
                                                   PiperClientService ◄─────┘
                                                    (ws://localhost:9000)
                                                               │
                                                    PCM Float32 audio
                                                               │
                                               Renvoyé au Client Android
                                               via ws_audio_service (tts_track)
```

---

## Structure des fichiers

```
agent-nvidia-v2/
├── main.py                        # Point d'entrée : composition root + routes FastAPI
├── config.py                      # Toutes les constantes et variables d'env
├── logging_setup.py               # Configuration du logger fichier
├── system_prompt.md               # Prompt système chargé par OllamaService
├── data.json                      # Livraisons du jour (exportées par PlanningService)
├── requirements.txt               # Dépendances Python
├── Modelfile                      # Config du modèle Ollama (Rytle)
│
├── models/
│   └── session.py                 # Dataclass Session (état complet par connexion WS)
│
├── services/
│   ├── __init__.py
│   ├── agent_service.py           # Orchestrateur principal STT→LLM→TTS
│   ├── audio_service.py           # Utilitaires audio (normalize, resample)
│   ├── vad_service.py             # Voice Activity Detection (Silero ONNX)
│   ├── whisper_service.py         # STT (faster-whisper, embarqué ou HTTP)
│   ├── new_ollama_service.py      # LLM service (Ollama, streaming, outils)
│   ├── ollama_service.py          # Shim (alias → new_ollama_service)
│   ├── piper_client_service.py    # Client TTS WebSocket → piper-server ws:9000
│   ├── tts_utils.py               # Utilitaires texte pour TTS (split phrases)
│   ├── denoise_service.py         # Débruitage DeepFilterNet (utterance-level)
│   ├── delivery_service.py        # Gestion livraisons (identification driver, trips)
│   ├── delivery_state_machine.py  # Machine à états (MODE_0 / MODE_1) livraison
│   ├── notification_service.py    # Bus de notifications WebSocket (pub/sub)
│   ├── websocket_service.py       # Transport WebSocket (sessions, routing messages)
│   └── ws_audio_service.py        # Pipeline audio WebSocket (decode, VAD, feed agent)
│
├── routers/
│   └── test_audio_router.py       # Routes de test audio (collecte données débruitage)
│
├── models/
│   └── session.py                 # Modèle de session (une par connexion WebSocket)
│
├── data_base_service/             # Couche d'accès aux données externes (API planning)
│   ├── entities/                  # Modèles de données (Trip, Driver, etc.)
│   │   ├── enum/
│   │   └── models/
│   └── service/                   # Services d'accès aux données
│       ├── __init__.py            # Exports (TokenManager…)
│       ├── planning_service.py    # Récupération trips via API externe
│       ├── crud_service.py        # CRUD API (search_driver, update trip status…)
│       ├── authentification.py    # Authentification OAuth2 / token
│       ├── token_manager.py       # Cache de token JWT (token_cache.md)
│       ├── http_request_services.py # Client HTTP async
│       └── logger_service.py      # Logger interne
│
├── experimental/
│   └── denoise_stream.py          # Débruitage en streaming temps réel (WIP)
│
├── web/
│   ├── index.html                 # Interface de test WebSocket vocale
│   └── record.html                # Interface d'enregistrement audio (test denoise)
│
├── assets/
│   ├── models/
│   │   ├── silero_vad.onnx        # Modèle VAD Silero
│   │   ├── en_US-lessac-high.onnx # Modèle TTS Piper (voix)
│   │   └── en_US-lessac-high.onnx.json
│   └── recordings/                # Enregistrements WAV sauvegardés (test denoise)
│
├── tests/                         # Suite de tests unitaires (pytest)
│   ├── conftest.py
│   ├── test_agent_service.py
│   ├── test_vad_service.py
│   ├── test_ollama_service.py
│   ├── test_delivery_state_machine_emotions.py
│   └── ...
│
├── logs/
│   └── server.log                 # Log principal
├── mascote.log                    # Log Ollama (legacy)
└── cli.log                        # Log CLI planning
```

---

## Description des services

### `WebSocketService` — Transport
**Fichier :** `services/websocket_service.py`

Point d'entrée WebSocket unique (`/ws`). Gère les sessions, route les messages JSON et binaires.

| Message entrant (JSON) | Action |
|---|---|
| `start` | Démarre le pipeline audio de la session |
| `stop` | Nettoyage de la session |
| `arrived` | Déclenche le flow de complétion livraison (MODE_1) |
| `photo_taken` / `photo_not_taken` | Réponse à `ask_photo_event` |
| `external_control` | Événements de contrôle génériques |
| `test_tts` | Test TTS depuis l'interface web |

| Message sortant (JSON) | Signification |
|---|---|
| `started` | Session initialisée, sample rates |
| `transcript` | Texte STT reconnu |
| `response` | Fragment LLM |
| `tts_stop_now` | Couper lecture audio côté client |
| `interrupted` | TTS interrompu |
| `emotion` | Émotion courante (idle/speaking/greeting…) |
| `ask_photo_event` | Demander une photo au livreur |
| `external_control` | Commande à envoyer à l'app Android |
| `notification` | Notification générique (trips_list, etc.) |

---

### `WebSocketAudioService` — Pipeline audio
**Fichier :** `services/ws_audio_service.py`

Reçoit les chunks PCM16 binaires du micro, les décode, les passe au VAD, puis déclenche l'agent en fin d'utterance.

**Flux :**
```
bytes PCM16 → decode (OpusDecoder) → mono float32 16kHz
→ VADService.process_chunk()
→ speech_start : agent.on_user_speech_start()   (interruption TTS si nécessaire)
→ utterance_end : agent.process_utterance_pcm()  (déclenche STT→LLM→TTS)
```

Émet aussi vers le client les chunks audio TTS reçus de Piper via `tts_track` (PCM16 binary frames).

---

### `VADService` — Voice Activity Detection
**Fichier :** `services/vad_service.py`

Modèle Silero VAD (ONNX) chargé une fois. Scorage par session (état RNN h/c stocké dans `Session`).

**Paramètres configurables** (dans `config.py`) :
- `VAD_SILENCE_THRESHOLD` = 0.85 (seuil de démarrage)
- `VAD_CONTINUE_THRESHOLD` = 0.5 (hysteresis)
- `VAD_SILENCE_DURATION_MS` = 250ms (durée silence → fin utterance)
- `VAD_MIN_SPEECH_MS` = 160ms (durée min parole)
- `VAD_PRE_ROLL_MS` = 400ms / `VAD_POST_ROLL_MS` = 300ms

---

### `WhisperService` — STT
**Fichier :** `services/whisper_service.py`

Deux modes (`WHISPER_MODE`) :
- **embedded** : `faster-whisper` chargé directement (CUDA int8), modèle `small`
- **http** : client HTTP vers serveur externe (legacy)

---

### `OllamaService` — LLM
**Fichier :** `services/new_ollama_service.py` (shim dans `ollama_service.py`)

Modèle : **Rytle** (custom Modelfile, API Ollama compatible OpenAI `/v1/chat/completions`)

**Deux modes de complétion :**
- `chat()` → non-streaming (bloquant)
- `stream_chat()` → streaming async generator (tokens en temps réel → Piper)

**Outils LLM déclarés (function calling) :**
| Outil | Action côté app |
|---|---|
| `start_navigation` | `com.avvc.maps.action.START_NAVIGATION` |
| `stop_navigation` | `com.avvc.maps.action.STOP_NAVIGATION` |
| `show_map` | `com.avvc.maps.action.RECENTER` |
| `get_deliveries` | Lecture `data.json` |
| `show_deliveries` | `com.avvc.maps.action.SHOW_DELIVERIES_LIST` |
| `get_delivery_info` | Lookup statique (base de données in-memory) |
| `ask_photo` | `ask_photo_event` WebSocket |
| `update_status` | Mise à jour statut local |

**Méthodes spécialisées pour la state machine :**
- `is_this_a_confirmation(msg)` → `YES / NO / UNKNOWN`
- `get_delivery_failure_reason_response(msg, reasons)` → numéro ou liste
- `generate_system_reply(instruction)` → message court pour le TTS

---

### `PiperClientService` — TTS
**Fichier :** `services/piper_client_service.py`

Client WebSocket vers un **serveur Piper externe** (`ws://localhost:9000`).

**Protocole (JSON → Piper server) :**
| Message | Effet |
|---|---|
| `tts_stream` + `text` | Envoi token par token (streaming LLM) |
| `tts_stream_flush` | Force la synthèse des derniers mots |
| `tts` + `text` | Synthèse d'un bloc complet (legacy) |
| `tts_interrupt` | Interruption immédiate |

**Protocole retour (binaire ← Piper server) :**
`[uint32 N][float32 x N]` — samples PCM Float32 à 22050Hz

Le service transmet les samples via callback `_on_tts_audio_chunk` → `AgentService` → `tts_track` → Client.

---

### `AgentService` — Orchestrateur IA
**Fichier :** `services/agent_service.py`

Cerveau du système. Coordonne STT, LLM, TTS.

**Pipeline principal :**
```
process_utterance_pcm(session, samples)
  → [optionnel] denoise
  → WhisperService.transcribe_pcm()
  → _process_transcription()
      ├── [MODE_1] DeliveryStateMachine.process_input()
      │     └── _play_tts_simple() si réponse
      └── [MODE_0] _stream_response()
            → OllamaService.stream_chat()
            → token par token → PiperClientService.stream_text()
            → flush()
```

**Gestion des interruptions :**
- `on_user_speech_start()` : interrompt le TTS en cours (sauf en MODE_1)
- `interrupt()` : annule `tts_task`, envoie `tts_stop_now`
- `_stop_current_tts_with_fade()` : fade-out 150ms avant remplacement

**Watchdog TTS :**
Tâche background qui surveille l'inactivité Piper (4s sans chunk) → repasse en `idle`.

**Actions externes (app Android) :**
| Action | Handler |
|---|---|
| `arrived` | `_handle_arrived_action()` → entre en MODE_1 |
| `started_navigation` | Log uniquement |
| `completed_delivery` | `state_machine.update_trip_status()` |
| `photo_taken` | `state_machine.handle_photo_response()` |
| `photo_not_taken` | Idem |

---

### `DeliveryStateMachine` — Machine à états livraison
**Fichier :** `services/delivery_state_machine.py`

Activée quand un driver arrive sur place (`arrived` + `trip_id`). Prend le contrôle du pipeline vocal (MODE_1).

**Modes :**
- **MODE_0** : flux normal STT → LLM → TTS
- **MODE_1** : flux dirigé (questions/réponses structurées)

**États MODE_1 :**

```
enter_mode_1()
     │
  STATE_1 (ASK_COMPLETION)
  "Is the delivery completed?"
     │
     ├── OUI  → STATE_4 (success) → STATE_5 (EXIT) → MODE_0
     │          + send MARK_DELIVERED event
     │          + annonce prochaine livraison
     │          + trigger start_navigation (3s delay)
     │
     ├── NON  → STATE_2 (ASK_REASON)
     │          "Which reason? 1-6 or say 'list'"
     │              │
     │              ├── Raison 1 (client absent) → STATE_6 (ASK_PHOTO)
     │              │   + send ask_photo_event
     │              │       │
     │              │       ├── photo_taken  → success flow → MODE_0
     │              │       └── photo_not_taken → failure flow → MODE_0
     │              │
     │              └── Raisons 2-6 → STATE_5 (EXIT) → MODE_0
     │                  + send MARK_FAILED event
     │                  + annonce prochaine livraison
     │
     └── INCONNU → retry (boucle infinie jusqu'à OUI/NON)
```

**Événements WebSocket envoyés à l'app Android :**
- `mark_delivered_event` : livraison marquée COMPLETED
- `mark_failed_event` : livraison marquée FAILED
- `ask_photo_event` : demande de photo (reason 1)
- `start_navigation_event` : démarrer navigation vers prochaine livraison
- `outcome_emotion` : émotion contextuelle (success/failure/last_delivery)

---

### `NotificationService` — Bus de notifications
**Fichier :** `services/notification_service.py`

Système pub/sub pour les messages WebSocket. Permet aux services d'enregistrer des handlers sur des types de messages.

**Handlers enregistrés (main.py) :**
- `identify_driver` → `DeliveryService.identify_driver()`
- `get_trips` → `DeliveryService._handle_get_trips_wrapper()`

---

### `DeliveryService` — Gestion des livraisons
**Fichier :** `services/delivery_service.py`

Interfaçage avec l'API planning externe via `data_base_service/`.

**Flux identify_driver :**
```
message identify_driver {driver_serial}
  → PlanningService.get_delivery_trips(driver_serial)
  → export data.json  (lu par le LLM via get_deliveries)
  → send trips_list notification → Android
  → OllamaService.speak_instruction() → "Hello X, you have N trips..."
```

---

### `DenoiseService` — Débruitage
**Fichier :** `services/denoise_service.py`

**DeepFilterNet** (ONNX), désactivé par défaut (`DENOISE_ENABLED=false`).

Deux modes :
- `DENOISE_BEFORE_VAD=false` (défaut) : denoise sur l'utterance complète avant STT
- `DENOISE_BEFORE_VAD=true` : denoise chunk par chunk avant VAD (plus lent)

---

## `data_base_service/` — Couche données

Interface avec l'API de planning externe (authentification OAuth2, CRUD trips/drivers).

| Fichier | Rôle |
|---|---|
| `service/planning_service.py` | `get_delivery_trips()`, export `data.json` |
| `service/crud_service.py` | `search_driver()`, `update_package_status()`, etc. |
| `service/authentification.py` | Login OAuth2, refresh token |
| `service/token_manager.py` | Cache token JWT dans `token_cache.md` |
| `service/http_request_services.py` | Client HTTP async (httpx) |
| `entities/models/` | Modèles Trip, Driver, Package… |
| `entities/enum/` | Énumérations statuts livraison |

---

## Routes FastAPI

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/` | Interface web de test (web/index.html) |
| `GET` | `/record` | Interface enregistrement denoise (web/record.html) |
| `GET` | `/health` | Health check global (tous services) |
| `GET` | `/api/list-recordings` | Liste WAV enregistrés |
| `POST` | `/api/save-audio-denoised` | Sauvegarde + denoise one-shot + métriques |
| `POST` | `/notifications/send/{client_id}` | Envoyer notification à un client |
| `POST` | `/notifications/broadcast` | Broadcast notification tous clients |
| `WS` | `/ws` | Point d'entrée WebSocket principal |
| `WS` | `/ws-denoise` | WebSocket débruitage temps réel (chunk par chunk) |
| *via router* | `/test-audio/*` | Routes test audio (collecte données) |

---

## Dépendances circulaires et résolution

Le projet a plusieurs dépendances circulaires résolues par injection tardive :

```
AgentService ←──────────────────────── WebSocketService
     │                                       ▲
     └──────── set_ws_service(ws) ───────────┘

OllamaService ←─────────────────────── WebSocketService
     │                                       ▲
     └──────── set_ws_service(ws) ───────────┘

DeliveryStateMachine ←──────────────── WebSocketService + AgentService
     │                                       ▲
     └──────── _ws_service, _agent_service ──┘

WebSocketAudioService ──────────────── WebSocketService
     │                                       ▲
     └──────── _ws_service ──────────────────┘

NotificationService ←───────────────── WebSocketService
     │                                       ▲
     └──────── set_ws_service(ws) ───────────┘

DeliveryService ←───────────────────── NotificationService + WebSocketService
```

---

## Ordre de démarrage (lifespan FastAPI)

1. `VADService.startup()` — charge Silero ONNX
2. `WhisperService.startup()` — charge faster-whisper
3. `OllamaService.startup()` — health check Ollama
4. `NotificationService.startup()`
5. `DeliveryService.startup()`
6. `DeliveryStateMachine.startup()`
7. `PiperClientService.startup()` — connexion WebSocket → piper-server
8. `DenoiseService.startup()` — charge DeepFilterNet (si activé)
9. `prewarm_services()` — préchauffage VAD, STT, LLM, TTS

**Arrêt (ordre inverse):** Piper → Denoise → Delivery → StateMachine → Notification → Ollama → Whisper → VAD

---

## Configuration clé (`config.py`)

| Variable | Défaut | Description |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0:8000` | Serveur FastAPI |
| `WHISPER_MODE` | `embedded` | `embedded` ou `http` |
| `WHISPER_MODEL` | `small` | Taille modèle faster-whisper |
| `WHISPER_DEVICE` | `cuda` | `cuda` ou `cpu` |
| `OLLAMA_URL` | `localhost:8080` | URL API Ollama |
| `OLLAMA_MODEL` | `Rytle:latest` | Modèle LLM |
| `OLLAMA_STREAM` | `true` | Streaming token par token |
| `PIPER_BIN_PATH` | `/home/server/piper/...` | Binaire Piper local |
| `DENOISE_ENABLED` | `false` | Activer DeepFilterNet |
| `VAD_SILENCE_THRESHOLD` | `0.85` | Seuil VAD démarrage |
| `VAD_SILENCE_DURATION_MS` | `250` | Délai fin utterance |
| `MAX_HISTORY` | `3` | Nb messages LLM gardés |
| `PREWARM_ON_STARTUP` | `true` | Préchauffage au démarrage |
| `TTS_FADE_OUT_MS` | `150` | Fondu sortant lors d'interruption |

---

## Technologies utilisées

| Composant | Technologie |
|---|---|
| Framework web | FastAPI + Uvicorn |
| WebSocket | `websockets` + FastAPI native |
| STT | faster-whisper (CTranslate2, CUDA) |
| LLM | Ollama (modèle Rytle, API OpenAI-compatible) |
| TTS | Piper (binaire externe, serveur WS sur port 9000) |
| VAD | Silero VAD (ONNX via onnxruntime) |
| Débruitage | DeepFilterNet (ONNX) |
| Audio decode | Opus / PCM16 |
| HTTP client | httpx (async) + requests (sync) |
| Tests | pytest + pytest-asyncio |
| Plateforme cible | NVIDIA Jetson Orin Nano 8GB (aarch64) |
