# Documentation — Endpoint de collecte audio `/test/audio/upload`

Ce endpoint permet à une application mobile d'envoyer un enregistrement audio avec ses métadonnées.
Le serveur sauvegarde l'audio brut, applique le débruitage, transcrit avec Whisper, et log tout dans un CSV.

---

## 1. Accès au serveur

Le serveur tourne sur le port **8000**.

| Contexte | URL de base |
|---|---|
| Réseau local (même Wi-Fi) | `http://<IP_DU_SERVEUR>:8000` |
| Depuis internet via ngrok | `https://<ID>.ngrok-free.app` |

> **Trouver l'IP locale du serveur (Linux) :**
> ```bash
> ip a | grep "inet " | grep -v 127
> # exemple de résultat : 192.168.1.42
> ```

> **Trouver l'URL ngrok :**  
> Voir la sortie du terminal où tourne `ngrok http 8000`.  
> L'URL ressemble à : `https://abcd1234.ngrok-free.app`

---

## 2. Endpoint principal

### `POST /test/audio/upload`

Envoi d'une session d'enregistrement : métadonnées + fichier audio.

#### Type de requête

```
Content-Type: multipart/form-data
```

#### Champs du formulaire

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `nom_driver` | `string` | ✅ | Prénom / identifiant du conducteur |
| `texte_lu` | `string` | ✅ | Le texte que le conducteur devait lire |
| `condition_lecture` | `string` | ✅ | Contexte d'enregistrement (ex: `"silence"`, `"bruit route"`, `"fenêtre ouverte"`) |
| `outil_debruitage` | `string` | ✅ | Outil utilisé côté client (ex: `"aucun"`, `"RNNoise"`, `"DeepFilterNet"`) |
| `audio` | `file` | ✅ | Le fichier audio — **WAV PCM 16 kHz mono recommandé** |

#### Réponse (JSON)

```json
{
  "numero": 1,
  "raw_path": "test_data/dennoise/records/raw/rawaudio_1.wav",
  "denoised_path": "test_data/dennoise/records/denoised/denoised_1.wav",
  "transcription": "Bonjour, ceci est un test d'enregistrement.",
  "nom_driver": "Jean",
  "texte_lu": "Bonjour, ceci est un test d'enregistrement.",
  "condition_lecture": "bruit de route",
  "outil_debruitage": "RNNoise"
}
```

| Champ | Description |
|---|---|
| `numero` | Numéro unique auto-incrémenté de l'enregistrement |
| `raw_path` | Chemin serveur de l'audio brut sauvegardé |
| `denoised_path` | Chemin serveur de l'audio débruité |
| `transcription` | Texte reconnu par Whisper sur l'audio débruité |

---

## 3. Endpoint bonus — Lire le CSV

### `GET /test/audio/records`

Retourne toutes les entrées du CSV sous forme JSON.

```http
GET http://<SERVEUR>:8000/test/audio/records
```

**Réponse :**
```json
{
  "records": [
    {
      "numero": "1",
      "nom_driver": "Jean",
      "texte_lu": "Bonjour, ceci est un test.",
      "condition_lecture": "silence",
      "outil_debruitage": "aucun",
      "chemin_raw": "test_data/dennoise/records/raw/rawaudio_1.wav",
      "chemin_denoised": "test_data/dennoise/records/denoised/denoised_1.wav",
      "transcription": "Bonjour ceci est un test."
    }
  ]
}
```

---

## 4. Tester avec cURL

Envoyer un fichier WAV existant :

```bash
curl -X POST "http://192.168.1.42:8000/test/audio/upload" \
  -F "nom_driver=Jean" \
  -F "texte_lu=Bonjour, ceci est un test d'enregistrement." \
  -F "condition_lecture=bruit de route" \
  -F "outil_debruitage=RNNoise" \
  -F "audio=@/chemin/vers/mon_enregistrement.wav"
```

Via ngrok :

```bash
curl -X POST "https://abcd1234.ngrok-free.app/test/audio/upload" \
  -F "nom_driver=Jean" \
  -F "texte_lu=Bonjour, ceci est un test d'enregistrement." \
  -F "condition_lecture=bruit de route" \
  -F "outil_debruitage=RNNoise" \
  -F "audio=@/chemin/vers/mon_enregistrement.wav"
```

---

## 5. Intégration mobile (Flutter / Dart)

```dart
import 'dart:io';
import 'package:http/http.dart' as http;

Future<void> sendAudioRecord({
  required String serverUrl,   // ex: "https://abcd1234.ngrok-free.app"
  required String nomDriver,
  required String texteL,
  required String conditionLecture,
  required String outilDebruitage,
  required File audioFile,
}) async {
  final uri = Uri.parse('$serverUrl/test/audio/upload');

  final request = http.MultipartRequest('POST', uri);

  // Métadonnées texte
  request.fields['nom_driver']        = nomDriver;
  request.fields['texte_lu']          = texteL;
  request.fields['condition_lecture'] = conditionLecture;
  request.fields['outil_debruitage']  = outilDebruitage;

  // Fichier audio
  request.files.add(
    await http.MultipartFile.fromPath(
      'audio',
      audioFile.path,
      // contentType: MediaType('audio', 'wav'), // optionnel
    ),
  );

  final streamedResponse = await request.send();
  final response = await http.Response.fromStream(streamedResponse);

  if (response.statusCode == 200) {
    print('✅ Succès : ${response.body}');
  } else {
    print('❌ Erreur ${response.statusCode} : ${response.body}');
  }
}
```

---

## 6. Intégration mobile (Swift / iOS)

```swift
import Foundation

func sendAudioRecord(
    serverURL: String,
    nomDriver: String,
    texteLu: String,
    conditionLecture: String,
    outilDebruitage: String,
    audioFileURL: URL,
    completion: @escaping (Result<Data, Error>) -> Void
) {
    guard let url = URL(string: "\(serverURL)/test/audio/upload") else { return }
    
    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    
    let boundary = "Boundary-\(UUID().uuidString)"
    request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
    
    var body = Data()
    
    func appendField(_ name: String, value: String) {
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
        body.append("\(value)\r\n".data(using: .utf8)!)
    }
    
    appendField("nom_driver",        value: nomDriver)
    appendField("texte_lu",          value: texteLu)
    appendField("condition_lecture", value: conditionLecture)
    appendField("outil_debruitage",  value: outilDebruitage)
    
    // Fichier audio
    if let audioData = try? Data(contentsOf: audioFileURL) {
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"audio.wav\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: audio/wav\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n".data(using: .utf8)!)
    }
    
    body.append("--\(boundary)--\r\n".data(using: .utf8)!)
    request.httpBody = body
    
    URLSession.shared.dataTask(with: request) { data, response, error in
        if let error = error { completion(.failure(error)); return }
        completion(.success(data ?? Data()))
    }.resume()
}
```

---

## 7. Intégration mobile (Python — test rapide)

```python
import requests

url = "http://192.168.1.42:8000/test/audio/upload"  # ou URL ngrok

with open("mon_enregistrement.wav", "rb") as f:
    response = requests.post(
        url,
        data={
            "nom_driver":        "Jean",
            "texte_lu":          "Bonjour, ceci est un test.",
            "condition_lecture": "bruit de route",
            "outil_debruitage":  "RNNoise",
        },
        files={
            "audio": ("enregistrement.wav", f, "audio/wav"),
        },
    )

print(response.status_code)
print(response.json())
```

---

## 8. Vérifier que le serveur est accessible

```bash
# Health check général
curl http://192.168.1.42:8000/health

# Ou via ngrok
curl https://abcd1234.ngrok-free.app/health
```

Réponse attendue :
```json
{"status": "ok", ...}
```

---

## 9. Structure des fichiers générés

```
test_data/dennoise/
├── records.csv                          ← journal de tous les enregistrements
└── records/
    ├── raw/
    │   ├── rawaudio_1.wav               ← audio brut reçu
    │   ├── rawaudio_2.wav
    │   └── ...
    └── denoised/
        ├── denoised_1.wav               ← audio après débruitage serveur
        ├── denoised_2.wav
        └── ...
```

### Format du CSV (`records.csv`)

| Colonne | Description |
|---|---|
| `numero` | Numéro unique de l'enregistrement |
| `nom_driver` | Nom du conducteur |
| `texte_lu` | Texte que le conducteur devait lire |
| `condition_lecture` | Contexte d'enregistrement |
| `outil_debruitage` | Outil de débruitage utilisé côté client |
| `chemin_raw` | Chemin relatif vers le fichier audio brut |
| `chemin_denoised` | Chemin relatif vers le fichier débruité |
| `transcription` | Transcription Whisper de l'audio débruité |

---

## 10. Codes d'erreur

| Code HTTP | Cause |
|---|---|
| `200` | Succès |
| `400` | Fichier audio vide ou absent |
| `422` | Format audio non supporté (utiliser WAV de préférence) |
| `500` | Erreur interne (sauvegarde disque, etc.) |
