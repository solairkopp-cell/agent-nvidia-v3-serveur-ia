# Client Audio WebSocket : comment communiquer avec le serveur

Ce guide explique comment un client doit communiquer avec le serveur vocal via WebSocket.

## URL WebSocket

Le serveur expose une seule URL WebSocket pour l'audio temps réel :

- `ws://<adresse>:8000/ws`

> Attention : le chemin exact est `/ws`. Si le client se connecte à `/` ou à une autre URL, le serveur renverra une erreur 403.

## Protocoles supportés

### 1) JSON client → serveur

Le client envoie d'abord un message JSON de démarrage :

```json
{ "type": "start", "input_sample_rate": 48000 }
```

- `type`: doit être `start`
- `input_sample_rate`: optionnel, fréquence d'échantillonnage du micro client (par ex. `48000`)

Autres messages JSON possibles :

```json
{ "type": "stop" }
```

```json
{ "type": "test_tts", "text": "Bonjour" }
```

Le serveur accepte aussi un certain nombre de messages métier et notifications, mais pour l'audio pur, `start`, `stop` et `test_tts` sont les plus importants.

### 2) Binaire client → serveur

Après le message `start`, le client peut envoyer des paquets audio binaires via WebSocket.

- Format attendu : PCM16 (16 bits signé), mono, little-endian
- Pas de WAV, pas de JSON, pas de base64
- Chaque message WebSocket binaire contient directement des échantillons PCM16

Le serveur convertit ensuite ces octets en `float32`, resample si besoin et traite la voix avec la VAD et le STT.

## Déroulé du client

1. Ouvrir la connexion WebSocket sur `ws://.../ws`
2. Envoyer `{ "type": "start", "input_sample_rate": 48000 }`
3. Attendre la réponse `started` du serveur
4. Envoyer des blobs binaires PCM16 mono
5. Lire les messages JSON du serveur et les frames audio binaires de sortie
6. Envoyer `{ "type": "stop" }` pour arrêter la session audio

## Que renvoie le serveur ?

### JSON serveur → client

- `started` : la session audio est prête
- `vad` : événements de détection de parole
- `transcript` : texte reconnu par STT
- `response` : texte de la réponse LLM
- `tts_test` : retour d'un test TTS
- `tts_stop_now` : demander au client de couper la lecture
- `interrupted` : TTS interrompu
- `error` : erreur serveur

Exemple `started` :

```json
{
  "type": "started",
  "input_sample_rate": 48000,
  "audio_output_sample_rate": 48000,
  "encoding": "pcm_s16le",
  "channels": 1,
  "auth_mode": "manual"
}
```

### Binaire serveur → client

Quand le serveur envoie du binaire, il s'agit de paquets audio TTS :

- PCM16 mono little-endian
- fréquence : `audio_output_sample_rate` donnée dans le message `started`

Le client doit lire ces octets comme de l'audio PCM brut.

## Exemple JavaScript (navigateur)

```js
const ws = new WebSocket('ws://<serveur>:8000/ws');
ws.binaryType = 'arraybuffer';

ws.onopen = () => {
  ws.send(JSON.stringify({ type: 'start', input_sample_rate: 48000 }));
};

ws.onmessage = (event) => {
  if (typeof event.data === 'string') {
    const msg = JSON.parse(event.data);
    console.log('JSON reçu', msg);
    return;
  }

  // event.data est un ArrayBuffer contenant du PCM16 de TTS
  const audioBuffer = event.data;
  console.log('Audio binaire reçu', audioBuffer.byteLength);
};

function sendPcm16Samples(int16Array) {
  ws.send(int16Array.buffer);
}

function stopSession() {
  ws.send(JSON.stringify({ type: 'stop' }));
}
```

## Exemple Python

```python
import asyncio
import json
import websockets

async def main():
    uri = 'ws://localhost:8000/ws'
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({'type': 'start', 'input_sample_rate': 48000}))

        async def receiver():
            async for message in ws:
                if isinstance(message, str):
                    data = json.loads(message)
                    print('JSON reçu:', data)
                else:
                    print('Audio binaire reçu', len(message), 'octets')

        receiver_task = asyncio.create_task(receiver())

        # Exemple d'envoi de silence en PCM16
        # En pratique, générer ou lire des données micro mono 16-bit little-endian.
        import struct
        samples = [0] * 1600
        pcm_bytes = b''.join(struct.pack('<h', s) for s in samples)
        await ws.send(pcm_bytes)

        await asyncio.sleep(2)
        await ws.send(json.dumps({'type': 'stop'}))
        receiver_task.cancel()

asyncio.run(main())
```

## Points importants

- Le serveur lit uniquement l'endpoint `/ws`
- Les paquets audio doivent être envoyés en tant que donnée binaire WebSocket
- `input_sample_rate` permet au serveur de resampler correctement
- Le serveur utilise `config.SAMPLE_RATE = 16000` en interne pour VAD/STT
- Le client doit traiter séparément les messages texte JSON et les messages audio binaires

## Pourquoi le serveur renvoie 403 ?

Si vous voyez des logs `WebSocket / 403`, c'est probablement que le client essaie de se connecter sur la mauvaise URL ou que l'entête WebSocket n'est pas valide.

- URL correcte : `ws://<serveur>:8000/ws`
- Mauvaise URL typique : `ws://<serveur>:8000/`

## Résumé rapide

- `start` → initialise la session
- binaire PCM16 → entrée micro
- JSON `started` → réponse de démarrage
- binaire serveur → sortie TTS
- `stop` → termine la session

Ce fichier décrit le protocole audio client/serveur et peut être utilisé comme référence pour implémenter un client Android, Web ou Python.
