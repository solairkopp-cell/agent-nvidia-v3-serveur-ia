# Serveur d'agent vocal

![Statut](https://img.shields.io/badge/statut-en%20developpement-yellow)
![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Plateforme](https://img.shields.io/badge/plateforme-Jetson%20aarch64%20%7C%20Linux-green)

Serveur FastAPI pour assistant vocal temps reel destine aux livreurs. Il recoit l'audio d'une application Android ou d'un client WebSocket, detecte les tours de parole, transcrit avec Whisper, pilote la logique livraison, genere une reponse LLM et renvoie le TTS en audio binaire. La cible principale est une Jetson sous JetPack, avec chemins de repli CPU pour le developpement.

## Architecture globale

| Fichier | Role |
|---|---|
| `main.py` | Point d'entree FastAPI, composition des services, routes HTTP et WebSocket. |
| `config.py` | Configuration centrale et valeurs par defaut lues depuis l'environnement. |
| `services/websocket_service.py` | Sessions WebSocket, messages JSON, audio binaire, keep-alive et routage. |
| `services/ws_audio_service.py` | Flux audio entrant, resampling, decoupage VAD et emission TTS. |
| `services/audio_service.py` | Conversion PCM16/float32, WAV, resampling et normalisation. |
| `services/vad_service.py` | Silero VAD ONNX, detection `speech_start` et `utterance_end`. |
| `services/whisper_service.py` | STT en mode `faster-whisper`, `openai-whisper` ou HTTP. |
| `services/agent_service.py` | Orchestration STT -> livraison/LLM -> TTS -> WebSocket. |
| `services/ollama_service.py` | Client LLM local compatible Ollama ou serveur llama. |
| `services/piper_client_service.py` | Client WebSocket vers le serveur Piper streaming sur `ws://localhost:9000/`. |
| `services/denoise_service.py` | Debruitage optionnel, actuellement RNNoise dans le code runtime. |
| `experimental/denoise_stream.py` | WebSocket experimental de debruitage base64 par chunks. |
| `services/delivery_service.py` | Identification livreur, recuperation des trajets et notifications livraison. |
| `services/delivery_state_machine.py` | Machine d'etat de completion de livraison. |
| `routers/test_audio_router.py` | Points HTTP de collecte audio, debruitage, transcription et CSV de test. |
| `models/session.py` | Etat d'une connexion client WebSocket. |
| `web/index.html` | Client Web de test pour conversation vocale. |
| `web/record.html` | Client Web de test pour enregistrement et debruitage. |
| `start_api.sh` | Lancement Uvicorn sur `0.0.0.0:8000`. |
| `start_llama.sh` | Lancement du serveur LLM local sur le port `8080`. |

## Prerequis

- Linux aarch64 sur Jetson, ou Linux x86_64 pour developpement.
- Python 3.10 ou plus recent. Version constatee localement : `Python 3.10.12`.
- JetPack avec CUDA si `WHISPER_DEVICE=cuda`.
- RAM recommandee : 8 Go minimum sur Jetson Orin Nano avec modele Whisper `small.en` quantifie.
- VRAM recommandee : 4 Go minimum pour STT CUDA leger ; utiliser `WHISPER_DEVICE=cpu` en cas d'OOM.
- Modele Silero VAD present a `assets/models/silero_vad.onnx`.
- Serveur LLM local accessible sur `OLLAMA_URL`, par defaut `http://localhost:8080`.
- Serveur Piper streaming accessible sur `ws://localhost:9000/`.
- Pour les tests Python : `pytest` doit etre installe.

## Installation

Depuis le clone local :

```bash
cd /home/server/server
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
```

Installer les dependances Python principales :

```bash
python -m pip install fastapi "uvicorn[standard]" numpy soundfile httpx websockets onnxruntime faster-whisper scipy soxr librosa python-multipart pytest
```

Installer les dependances optionnelles selon la cible :

```bash
python -m pip install openai-whisper rnnoise
```

Verifier les modeles locaux :

```bash
cd /home/server/server
test -f assets/models/silero_vad.onnx
```

Verifier la syntaxe Python et shell :

```bash
cd /home/server/server
python -m py_compile config.py main.py services/*.py routers/*.py models/*.py experimental/*.py
bash -n start_api.sh
bash -n start_llama.sh
```

## Configuration

| Variable | Description | Defaut |
|---|---|---|
| `LOG_LEVEL` | Niveau de logs. | `INFO` |
| `LOG_FILE_PATH` | Fichier JSONL de logs serveur. | `logs/server-logs.jsonl` |
| `HOST` | Adresse d'ecoute Uvicorn. | `0.0.0.0` |
| `PORT` | Port HTTP/WebSocket. | `8000` |
| `WHISPER_MODE` | Mode STT : `embedded` ou `http`. | `embedded` |
| `WHISPER_URL` | URL STT HTTP si `WHISPER_MODE=http`. | `http://localhost:8080/inference` |
| `WHISPER_TIMEOUT` | Timeout STT HTTP en secondes. | `30` |
| `WHISPER_LANGUAGE` | Langue forcee pour Whisper ; vide pour auto. | `en` |
| `WHISPER_MODEL` | Modele Whisper charge en embedded. | `small.en` |
| `WHISPER_DEVICE` | Peripherique STT : `cuda` ou `cpu`. | `cuda` |
| `WHISPER_COMPUTE_TYPE` | Type de calcul faster-whisper. | `int8` |
| `WHISPER_BEAM_SIZE` | Beam size STT. | `1` |
| `WHISPER_BACKEND` | Backend embedded : `faster-whisper` ou `whisper`. | `faster-whisper` |
| `WHISPER_PROMPT` | Prompt initial court pour commandes livraison/navigation. | `delivery navigation map show the map start navigation show map delivery yes no ` |
| `PIPER_BIN_PATH` | Chemin du binaire Piper local. | `/home/server/piper/piper/piper` |
| `OLLAMA_URL` | URL du serveur LLM local. | `http://localhost:8080` |
| `OLLAMA_MODEL` | Nom du modele LLM. | `Rytle:latest` |
| `OLLAMA_STREAM` | Active le streaming LLM. | `true` |
| `OLLAMA_TEMPERATURE` | Temperature de generation. | `0.7` |
| `SYSTEM_PROMPT_PATH` | Fichier de prompt systeme. | `system_prompt.md` |
| `PIPER_MODEL_PATH` | Chemin du modele Piper ONNX. | `assets/models/en_US-lessac-high.onnx` |
| `PIPER_CONFIG_PATH` | Chemin de la config Piper JSON. | `assets/models/en_US-lessac-high.onnx.json` |
| `TTS_FADE_OUT_MS` | Duree de fade-out en interruption TTS. | `150` |
| `DENOISE_ENABLED` | Active le debruitage serveur. | `false` |
| `DENOISE_BACKEND` | Nom logique du backend debruitage. | `deepfilternet` |
| `DENOISE_BEFORE_VAD` | Debruite les chunks avant VAD. | `false` |
| `DENOISE_FOR_STT` | Debruite l'utterance avant STT. | `false` |
| `SAMPLE_RATE` | Frequence interne audio/VAD/STT. | `16000` |
| `AUDIO_OUTPUT_SAMPLE_RATE` | Frequence audio TTS envoyee au client. | `48000` |
| `VAD_CHUNK_MS` | Taille d'un chunk VAD Silero. | `32` |
| `VAD_SILENCE_THRESHOLD` | Seuil de depart de parole. | `0.85` |
| `VAD_START_TRIGGER_CHUNKS` | Chunks voix consecutifs avant `speech_start`. | `2` |
| `VAD_CONTINUE_THRESHOLD` | Seuil hysteresis pendant parole. | `0.5` |
| `VAD_SILENCE_DURATION_MS` | Silence requis pour finir une utterance. | `250` |
| `VAD_MIN_SPEECH_MS` | Duree minimale d'une utterance acceptee. | `160` |
| `VAD_PRE_ROLL_MS` | Audio conserve avant debut parole. | `400` |
| `VAD_POST_ROLL_MS` | Audio conserve apres fin detectee. | `300` |
| `VAD_MAX_UTTERANCE_MS` | Duree maximale forcee d'une utterance. | `6000` |
| `SILERO_MODEL_PATH` | Chemin du modele Silero VAD ONNX. | `assets/models/silero_vad.onnx` |
| `PREWARM_ON_STARTUP` | Prechauffage VAD/STT au demarrage. | `true` |
| `PREWARM_TIMEOUT_SEC` | Timeout par etape de warmup. | `20` |
| `PREWARM_LLM_TEXT` | Texte de warmup LLM, conserve pour compatibilite config. | `hello what's your name?` |
| `PREWARM_TTS_TEXT` | Texte de warmup TTS, conserve pour compatibilite config. | `Warmup.` |
| `MAX_HISTORY` | Taille max avant trim de l'historique conversation. | `3` |
| `TRIM_TO` | Nombre de messages conserves au trim. | `30` |
| `PIPER_NOISE_SCALE` | Parametre voix Piper. | `1.0` |
| `PIPER_LENGTH_SCALE` | Parametre vitesse/duree Piper. | `0.9` |
| `PIPER_NOISE_W` | Parametre prosodie Piper. | `1.0` |
| `PIPER_SENTENCE_SILENCE` | Silence entre phrases Piper. | `0.8` |
| `PIPER_ESPEAK_DATA` | Chemin espeak-ng sur Jetson aarch64. | `/usr/lib/aarch64-linux-gnu/espeak-ng-data` |

## Lancement

Demarrer le LLM local si le binaire et le modele existent :

```bash
cd /home/server/server
bash start_llama.sh
```

Demarrer l'API :

```bash
cd /home/server/server
bash start_api.sh
```

Lancement direct equivalent :

```bash
cd /home/server/server
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Interfaces locales :

```bash
curl http://localhost:8000/health
```

- Assistant Web : `http://localhost:8000/`
- Enregistrement audio : `http://localhost:8000/record`
- WebSocket Android : `ws://<ip-jetson>:8000/ws`

## Pipeline audio

Schema complet :

```text
Android/Web
  | JSON {"type":"start","input_sample_rate":48000}
  v
WebSocketService /ws
  | binaire PCM16 mono little-endian
  v
WebSocketAudioService
  | decode PCM16 -> float32, resample vers 16000 Hz
  v
VADService Silero ONNX
  | speech_start -> interruption TTS si besoin
  | utterance_end -> buffer audio complet
  v
DenoiseService optionnel
  | seulement si DENOISE_FOR_STT=true
  v
WhisperService
  | transcript JSON {"type":"transcript","text":"..."}
  v
AgentService
  | machine d'etat livraison si MODE_1, sinon LLM
  v
OllamaService
  | chunks JSON {"type":"response","text":"..."}
  v
PiperClientService
  | texte vers ws://localhost:9000/
  | retour Float32 PCM depuis Piper
  v
AudioSocketOutput
  | binaire PCM16 mono a AUDIO_OUTPUT_SAMPLE_RATE
  v
Android/Web
```

Details :

- Le client envoie du PCM16 mono little-endian en messages WebSocket binaires.
- Le serveur accepte un `input_sample_rate` client et resample vers `SAMPLE_RATE=16000`.
- Silero traite des chunks de `32 ms`, soit `512` samples a 16 kHz.
- `speech_start` envoie un evenement VAD et peut interrompre le TTS courant.
- `utterance_end` cree une tache asynchrone STT -> Intent/livraison -> TTS.
- Le TTS retourne du binaire PCM16 mono ; le client utilise `audio_output_sample_rate` annonce au demarrage.

## Points de supervision

| Methode | Path | Description |
|---|---|---|
| `GET` | `/health` | Etat global et disponibilite des services. |
| `GET` | `/api/list-recordings` | Liste des enregistrements audio sauvegardes. |
| `POST` | `/api/save-audio-denoised` | Sauvegarde un audio PCM16 base64 et ses metriques. |
| `POST` | `/notifications/send/{client_id}` | Envoie une notification a une session WebSocket. |
| `POST` | `/notifications/broadcast` | Diffuse une notification a toutes les sessions. |
| `POST` | `/test/audio/upload` | Upload multipart audio de test, sauvegarde raw/denoised, transcrit et logue le CSV. |
| `GET` | `/test/audio/records` | Retourne le contenu du CSV de collecte audio. |
| `GET` | `/` | Page Web de test, hors schema API. |
| `GET` | `/record` | Page Web d'enregistrement, hors schema API. |

Exemple `GET /health` :

```json
{
  "status": "ok",
  "sessions": 0,
  "audio_streams": 0,
  "services": {
    "ws": true,
    "audio_stream": true,
    "whisper": true,
    "notification": true,
    "delivery": true,
    "state_machine": true,
    "denoise": true
  }
}
```

Exemple `GET /api/list-recordings` constate localement :

```json
{
  "files": [
    "audio_ff17afb2-d782-4e77-9e0f-0800f0d24c41_03ecbe53_raw.wav",
    "audio_ff17afb2-d782-4e77-9e0f-0800f0d24c41_03ecbe53_denoised.wav",
    "audio_fee93533-85bf-4ef7-b712-3087129dade4_f9c9717f_raw.wav"
  ]
}
```

Exemple `POST /api/save-audio-denoised` sans audio :

```json
{
  "error": "No audio data provided"
}
```

Exemple `POST /api/save-audio-denoised` avec `raw_audio` ou `audio` :

```json
{
  "id": "0abad7ed",
  "filename": "recording_0abad7ed_denoised.wav",
  "url": "/assets/recordings/recording_0abad7ed_denoised.wav",
  "raw_filename": "recording_0abad7ed_raw.wav",
  "raw_url": "/assets/recordings/recording_0abad7ed_raw.wav",
  "metrics": {
    "raw": {
      "samples": 16000,
      "duration_ms": 1000,
      "rms": 0.0,
      "peak": 0.0
    },
    "denoised": {
      "samples": 16000,
      "duration_ms": 1000,
      "rms": 0.0,
      "peak": 0.0
    }
  }
}
```

Exemple `POST /notifications/send/{client_id}` si le client existe :

```json
{
  "sent": true,
  "message": "Notification sent"
}
```

Exemple `POST /notifications/send/{client_id}` si le client est absent :

```json
[
  {
    "sent": false,
    "message": "Client not found"
  },
  404
]
```

Exemple `POST /notifications/broadcast` sans client connecte :

```json
{
  "sent": true,
  "count": 0
}
```

Exemple `GET /test/audio/records` sans CSV :

```json
{
  "records": []
}
```

Exemple `POST /test/audio/upload` :

```json
{
  "numero": 1,
  "raw_path": "test_data/dennoise/records/raw/rawaudio_1.wav",
  "denoised_path": "test_data/dennoise/records/denoised/denoised_1.wav",
  "transcription": "",
  "nom_driver": "Alice",
  "texte_lu": "Delivery completed",
  "condition_lecture": "silencieux",
  "outil_debruitage": "aucun"
}
```

## WebSocket

| Point WebSocket | Port | Codec | Format audio | Role |
|---|---:|---|---|---|
| `/ws` | `8000` | PCM16 little-endian | Mono, entree annoncee par Android, traitement interne 16 kHz, sortie `AUDIO_OUTPUT_SAMPLE_RATE` | Conversation vocale complete. |
| `/ws-denoise` | `8000` | JSON base64 PCM16 | Mono 16 kHz | Debruitage experimental par chunks. |

Connexion Android sur `/ws` :

```text
1. Ouvrir ws://<ip-jetson>:8000/ws
2. Envoyer {"type":"start","input_sample_rate":48000}
3. Recevoir {"type":"started","input_sample_rate":48000,"audio_output_sample_rate":48000,"encoding":"pcm_s16le","channels":1}
4. Envoyer les frames micro en messages binaires PCM16 mono little-endian.
5. Ecouter les messages JSON: vad, transcript, response, emotion, notification, error.
6. Lire les messages binaires serveur comme audio TTS PCM16 mono.
7. Envoyer {"type":"stop"} avant fermeture propre.
```

Connexion Android avec identification du livreur :

```text
Option 1 - code tape:
1. Ouvrir ws://<ip-jetson>:8000/ws
2. Envoyer {"type":"start","input_sample_rate":48000}
3. Envoyer {"type":"identify_driver","driver_serial":"00123"}
4. Attendre une notification "trips_list", "no_trips" ou "error".

Option 2 - code dicte:
1. Ouvrir ws://<ip-jetson>:8000/ws
2. Envoyer {"type":"start","input_sample_rate":48000,"auth_mode":"voice_driver_serial"}
3. Lire le TTS serveur: "Welcome driver, identify yourself. Please say your driver number."
4. Envoyer le micro en PCM16 mono comme pour une conversation normale.
5. Le serveur transcrit avec Whisper, extrait les chiffres dans l'ordre, puis appelle identify_driver.
6. Ecouter les evenements JSON "auth" pour afficher l'etat cote UI.
```

Texte d'integration Android :

```text
L'application peut proposer deux modes d'identification. Si le livreur tape son code, envoyer simplement {"type":"identify_driver","driver_serial":"..."} apres le message start. Si le livreur veut s'identifier a la voix, envoyer start avec "auth_mode":"voice_driver_serial", demarrer tout de suite le streaming micro PCM16 mono, puis attendre les evenements "auth". Quand le serveur detecte le numero, il envoie {"type":"auth","event":"driver_serial_detected","driver_serial":"..."} puis reutilise le flux existant de livraison: notification "trips_list" si des trajets existent, ou "no_trips" sinon.
```

Guide client Android :

```text
Connexion WebSocket:
1. Construire l'URL: ws://<ip-jetson>:8000/ws
2. Ouvrir un WebSocket avec OkHttp, Ktor ou la librairie WebSocket Android choisie.
3. Attendre onOpen avant d'envoyer le premier JSON.

Mode code tape:
1. onOpen -> envoyer {"type":"start","input_sample_rate":48000}
2. Attendre {"type":"started",...}
3. Quand le livreur valide le champ texte, envoyer {"type":"identify_driver","driver_serial":"00123"}
4. Attendre:
   - {"type":"auth","event":"driver_identified","driver_serial":"00123"}
   - puis {"type":"notification","notification_type":"trips_list",...}
   - ou {"type":"notification","notification_type":"no_trips",...}
   - ou {"type":"notification","notification_type":"error",...}

Mode code dicte:
1. onOpen -> envoyer {"type":"start","input_sample_rate":48000,"auth_mode":"voice_driver_serial"}
2. Attendre {"type":"started",...}
3. Preparer la lecture audio avec audio_output_sample_rate recu dans started.
4. Lire les messages binaires serveur: le prompt TTS arrive en PCM16 mono.
5. Demarrer le micro Android et envoyer les frames PCM16 mono little-endian en binaire WebSocket.
6. Le livreur dit son numero, par exemple: "zero zero one two three".
7. Continuer a envoyer le micro pendant que le serveur detecte VAD -> Whisper -> numero.
8. Attendre {"type":"auth","event":"driver_serial_detected","driver_serial":"00123",...}
9. Si le serveur envoie {"type":"auth","event":"driver_serial_not_understood",...}, garder le micro ouvert: le serveur redemande vocalement le numero.
10. Quand {"type":"auth","event":"driver_identified",...} arrive, le livreur est connecte.
```

Pseudo-code Android :

```text
onWebSocketOpen:
  if mode == CODE_TAPE:
    sendText({"type":"start","input_sample_rate":48000})
  if mode == CODE_VOCAL:
    sendText({"type":"start","input_sample_rate":48000,"auth_mode":"voice_driver_serial"})

onTextMessage(json):
  if json.type == "started":
    outputRate = json.audio_output_sample_rate
    preparePcm16Player(sampleRate = outputRate, channels = 1)
    if mode == CODE_VOCAL:
      startMicrophonePcm16Streaming(sampleRate = 48000, channels = 1)

  if json.type == "auth" and json.event == "driver_serial_detected":
    showDetectedCode(json.driver_serial)

  if json.type == "auth" and json.event == "driver_serial_not_understood":
    showMessage("Numero non compris, repetez votre code")

  if json.type == "auth" and json.event == "driver_identified":
    showMessage("Livreur identifie")

  if json.type == "notification" and json.notification_type == "trips_list":
    displayTrips(json.data.trips)

onBinaryMessage(bytes):
  playPcm16Mono(bytes, sampleRate = outputRate)

onTypedCodeValidated(code):
  sendText({"type":"identify_driver","driver_serial":code})

onMicrophoneFrame(pcm16Bytes):
  sendBinary(pcm16Bytes)
```

Contraintes audio Android :

```text
- Envoyer uniquement du PCM16 mono little-endian.
- Le sample rate envoye dans input_sample_rate doit correspondre au micro Android.
- Si le micro capture en 48000 Hz, envoyer input_sample_rate=48000.
- Ne pas encoder en WAV, AAC, Opus ou Base64 pour /ws: les frames micro sont binaires brutes.
- La sortie TTS serveur est aussi du PCM16 mono binaire.
- Utiliser audio_output_sample_rate du message started pour lire correctement le TTS.
- Garder le WebSocket ouvert apres identification: la meme connexion sert ensuite a la conversation et aux evenements livraison.
```

Messages JSON client vers serveur :

| Message | Description |
|---|---|
| `{"type":"start","input_sample_rate":48000}` | Initialise le flux audio. |
| `{"type":"start","input_sample_rate":48000,"auth_mode":"voice_driver_serial"}` | Initialise le flux audio et demande l'identification vocale du driver. |
| `{"type":"start_voice_auth"}` | Lance l'identification vocale apres un `start` deja effectue. |
| `{"type":"identify_driver","driver_serial":"00123"}` | Identifie le driver avec un code tape cote client. |
| `{"type":"stop"}` | Nettoie la session audio et retourne `{"type":"stopped"}`. |
| `{"type":"test_tts","text":"Test audio."}` | Joue un texte via Piper, exige `start` avant. |
| `{"type":"arrived","id":"trip_id"}` | Declenche le controle externe d'arrivee livraison. |
| `{"type":"photo_taken"}` | Reponse positive a une demande de photo. |
| `{"type":"photo_not_taken"}` | Reponse negative a une demande de photo. |
| `{"type":"external_control","action":"arrived","extras":{"trip_id":"..."}}` | Controle externe generique. |
| `{"type":"read_next_instruction"}` | Ignore volontairement par le serveur. |

Messages JSON serveur vers client :

| Type | Exemple |
|---|---|
| `started` | `{"type":"started","input_sample_rate":48000,"audio_output_sample_rate":48000,"encoding":"pcm_s16le","channels":1}` |
| `stopped` | `{"type":"stopped"}` |
| `vad` | `{"type":"vad","event":"speech_start","p":0.91}` |
| `transcript` | `{"type":"transcript","text":"show the map"}` |
| `response` | `{"type":"response","text":"Starting navigation."}` |
| `auth_prompt` | `{"type":"auth_prompt","text":"Welcome driver, identify yourself. Please say your driver number."}` |
| `tts_test` | `{"type":"tts_test","text":"Test audio."}` |
| `tts_stop_now` | `{"type":"tts_stop_now"}` |
| `interrupted` | `{"type":"interrupted"}` |
| `stt_empty` | `{"type":"stt_empty"}` |
| `auth` | `{"type":"auth","event":"driver_serial_detected","driver_serial":"00123","transcript":"zero zero one two three"}` |
| `emotion` | `{"type":"emotion","name":"speaking"}` |
| `notification` | `{"type":"notification","notification_type":"trips_list","data":{}}` |
| `ask_photo_event` | `{"type":"ask_photo_event"}` |
| `external_control` | `{"type":"external_control","action":"started_navigation","extras":{}}` |
| `error` | `{"type":"error","message":"unknown type"}` |

WebSocket `/ws-denoise` :

```text
Client -> serveur: {"audio":"AAA="}
Serveur -> client: {"status":"buffering","buffered_ms":0,"message":"Accumulating: 0ms / 100ms"}
Client -> serveur: {"final":true}
Serveur -> client: {"status":"ok","audio":"","message":"No buffered audio","final":true}
Client -> serveur: {"reset":true}
Serveur -> client: {"status":"ok","message":"Buffer reset"}
```

## Deploiement Jetson

- Architecture cible : `aarch64`.
- Chemin espeak par defaut : `/usr/lib/aarch64-linux-gnu/espeak-ng-data`.
- `PIPER_BIN_PATH` pointe vers `/home/server/piper/piper/piper`; verifier que le binaire est compile pour aarch64.
- `soxr` est utilise en priorite pour le resampling ; `scipy` puis `librosa` servent de replis.
- `faster-whisper` utilise CTranslate2 ; sur Jetson, commencer avec `WHISPER_MODEL=small.en`, `WHISPER_COMPUTE_TYPE=int8`.
- Si CTranslate2/CUDA est instable, passer `WHISPER_DEVICE=cpu`.
- Le README historique mentionnait DeepFilterNet3 ; le code runtime actuel importe `rnnoise`. Garder `DENOISE_ENABLED=false` tant que le backend natif n'est pas installe et valide sur la Jetson.
- `VADService` essaie les providers ONNX Runtime dans cet ordre si disponibles : CUDA, CPU, TensorRT ajoute en dernier.
- Le script `start_llama.sh` attend `llama-server` et le modele `/home/server/models/Qwen_Qwen3.5-4B-Q4_K_L.gguf`.

Commandes utiles Jetson :

```bash
uname -m
python --version
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
python -c "import soxr, numpy; print('soxr ok')"
```

## Depannage

| Erreur | Cause | Fix |
|---|---|---|
| `No module named pytest` | Les dependances de test ne sont pas installees dans l'environnement courant. | Activer le venv puis lancer `python -m pip install pytest`. |
| `Dependency 'onnxruntime' is required for VADService` | ONNX Runtime absent. | Installer `onnxruntime` ou une wheel Jetson compatible. |
| `Silero VAD ONNX model not found` | `assets/models/silero_vad.onnx` absent ou chemin incorrect. | Telecharger le modele ou definir `SILERO_MODEL_PATH`. |
| `Dependency 'faster-whisper' is not installed` | Backend STT par defaut absent. | Installer `faster-whisper` ou definir `WHISPER_BACKEND=whisper`. |
| `WhisperService not started` | Appel STT avant lifespan FastAPI ou startup echoue. | Demarrer via Uvicorn et verifier `/health`. |
| `Erreur de connexion au serveur Piper` | Aucun serveur Piper streaming sur `ws://localhost:9000/`. | Demarrer le serveur Piper ou adapter `PiperClientService(uri=...)`. |
| `Denoise streaming processor unavailable` | `DENOISE_ENABLED=false` ou backend debruitage non pret. | Installer le backend natif puis lancer avec `DENOISE_ENABLED=true`. |
| `start failed: ...` sur WebSocket | Erreur au demarrage de session audio. | Verifier le message `error`, les logs et la valeur `input_sample_rate`. |
| Audio trop rapide ou trop lent cote Android | Mauvais sample rate de lecture TTS. | Utiliser `audio_output_sample_rate` du message `started`. |
| STT vide avec audio valide | VAD trop strict, parole trop courte ou gain micro faible. | Baisser `VAD_SILENCE_THRESHOLD`, augmenter gain micro, verifier `VAD_MIN_SPEECH_MS`. |
| OOM CUDA sur Jetson | Modele STT ou provider CUDA trop lourd. | Utiliser `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`, modele `tiny` ou `small.en`. |
| `llama-server: command not found` | Serveur LLM local non installe dans le PATH. | Installer llama.cpp ou corriger `start_llama.sh`. |
| `Client not found` sur notification | `client_id` absent des sessions WebSocket actives. | Reconnecter le client et utiliser son `client_id` courant cote serveur. |

## Licence

Licence non precisee dans ce depot. Ajouter un fichier `LICENSE` avant publication.
