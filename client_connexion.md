# Guide de Connexion Client

Ce document explique comment un client (application mobile, web, etc.) doit se connecter au serveur et communiquer via WebSocket.

---

## 📡 Architecture de Communication

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLIENT                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ WebSocket   │  │ WebRTC      │  │ Notification Handlers   │  │
│  │ Signaling   │  │ Audio/Video │  │ (réception messages)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                    │
         │ WebSocket (ws://)  │ WebRTC (SDP + ICE)
         │                    │
         └────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SERVEUR                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ WebSocket   │  │ WebRTC      │  │ Notification            │  │
│  │ Service     │  │ Service     │  │ Service                 │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔌 1. Connexion WebSocket

### Étape 1 : Ouvrir la connexion

```javascript
// URL du serveur
const WS_URL = "ws://localhost:8000/ws";

// Ouvrir la connexion WebSocket
const websocket = new WebSocket(WS_URL);

// Gérer les événements de connexion
websocket.onopen = () => {
  console.log("✅ Connecté au serveur");
};

websocket.onclose = () => {
  console.log("❌ Déconnecté du serveur");
};

websocket.onerror = (error) => {
  console.error("⚠️ Erreur WebSocket:", error);
};
```

---

## 📨 2. Envoyer des Messages au Serveur

### Format des messages

Tous les messages envoyés au serveur doivent être au format JSON avec un champ `type` obligatoire.

```javascript
function sendMessage(type, data = {}) {
  const message = { type, ...data };
  websocket.send(JSON.stringify(message));
}
```

---

### Types de Messages Supportés

#### A. Messages WebRTC (Signalisation)

| Type | Description | Données |
|------|-------------|---------|
| `offer` | Offre SDP WebRTC | `{ sdp: "..." }` |
| `ice` | Candidat ICE | `{ candidate: {...} }` |
| `start` | Démarrer la session WebRTC | `{}` |
| `stop` | Arrêter la session WebRTC | `{}` |

**Exemple : Envoyer une offre SDP**
```javascript
sendMessage("offer", {
  sdp: "v=0\r\no=- 1234567890..."
});
```

**Exemple : Envoyer un candidat ICE**
```javascript
sendMessage("ice", {
  candidate: {
    candidate: "candidate:1234567890 udp 2122260223 192.168.1.1 54321 typ host",
    sdpMid: "0",
    sdpMLineIndex: 0
  }
});
```

---

#### B. Messages de Notification (Personnalisés)

| Type | Description | Données |
|------|-------------|---------|
| `client_location` | Envoyer sa position | `{ latitude: ..., longitude: ... }` |
| `delivery_update` | Mettre à jour une livraison | `{ package_id: "...", status: "..." }` |
| *tout autre type* | Message personnalisé | `{ ... }` |

**Exemple : Envoyer sa localisation**
```javascript
sendMessage("client_location", {
  latitude: 48.8566,
  longitude: 2.3522
});
```

**Exemple : Mettre à jour une livraison**
```javascript
sendMessage("delivery_update", {
  package_id: "PKG-123",
  status: "delivered"
});
```

**Exemple : Message personnalisé**
```javascript
sendMessage("custom_action", {
  action: "start_route",
  data: { route_id: "R-456" }
});
```

---

#### C. Messages de Test

| Type | Description | Données |
|------|-------------|---------|
| `test_tts` | Tester la synthèse vocale | `{ text: "..." }` |

**Exemple : Tester le TTS**
```javascript
sendMessage("test_tts", {
  text: "Bonjour, ceci est un test de synthèse vocale."
});
```

---

## 📥 3. Recevoir des Messages du Serveur

### Écouter les messages entrants

```javascript
websocket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleMessage(message);
};

function handleMessage(message) {
  const { type } = message;
  
  switch (type) {
    // Réponses WebRTC
    case "answer":
      handleWebRTCAnswer(message.sdp);
      break;
    
    case "ice":
      handleIceCandidate(message.candidate);
      break;
    
    // Transcription et réponses
    case "transcript":
      console.log("📝 Transcription:", message.text);
      break;
    
    case "response":
      console.log("🤖 Réponse LLM:", message.text);
      break;
    
    // Notifications
    case "notification":
      handleNotification(message.notification_type, message.data);
      break;
    
    // État VAD
    case "vad":
      handleVadEvent(message.event, message.p);
      break;
    
    // Interruptions
    case "interruption_decision":
      console.log("🔔 Décision d'interruption:", message.decision);
      break;
    
    case "interrupted":
      console.log("⚡ TTS interrompu");
      break;
    
    case "tts_stop_now":
      stopAudioPlayback();
      break;
    
    // Erreurs
    case "error":
      console.error("❌ Erreur serveur:", message.message);
      break;
    
    default:
      console.log("📨 Message inconnu:", message);
  }
}
```

---

### Types de Messages Reçus

#### A. Messages WebRTC

| Type | Description | Données |
|------|-------------|---------|
| `answer` | Réponse SDP WebRTC | `{ sdp: "..." }` |
| `ice` | Candidat ICE du serveur | `{ candidate: {...} }` |

---

#### B. Transcription et Réponses

| Type | Description | Données |
|------|-------------|---------|
| `transcript` | Texte transcrit par le STT | `{ text: "..." }` |
| `response` | Fragment de réponse LLM | `{ text: "..." }` |
| `intent` | Intention détectée | `{ intent: "start_navigation" }` |

---

#### C. Notifications

| Type | Description | Données |
|------|-------------|---------|
| `notification` | Notification personnalisée | `{ notification_type: "...", data: {...} }` |

**Exemple de notification reçue :**
```json
{
  "type": "notification",
  "notification_type": "new_delivery",
  "data": {
    "package_id": "PKG-123",
    "address": "123 Main Street",
    "client_name": "John Doe"
  }
}
```

**Handler de notification :**
```javascript
function handleNotification(notificationType, data) {
  switch (notificationType) {
    case "new_delivery":
      console.log("📦 Nouvelle livraison:", data);
      showDeliveryNotification(data);
      break;
    
    case "route_updated":
      console.log("🗺️ Itinéraire mis à jour:", data);
      updateMapRoute(data);
      break;
    
    case "system_message":
      console.log("📢 Message système:", data);
      showSystemMessage(data.message);
      break;
    
    default:
      console.log("🔔 Notification inconnue:", notificationType, data);
  }
}
```

---

#### D. État VAD (Voice Activity Detection)

| Type | Description | Données |
|------|-------------|---------|
| `vad` | Événement de détection vocale | `{ event: "speech_start" | "utterance_end", p: 0.95 }` |

---

#### E. Interruptions

| Type | Description | Données |
|------|-------------|---------|
| `interruption_decision` | Décision d'interruption | `{ decision: "continuation" | "interruption", elapsed_ms: 500, text: "..." }` |
| `interrupted` | TTS interrompu | `{}` |
| `tts_stop_now` | Arrêt immédiat du TTS | `{}` |

---

## 🔄 4. Flux de Communication Complet

### Exemple : Session WebRTC + Notifications

```javascript
class VoiceClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.pc = null; // RTCPeerConnection
    this.clientId = null;
    
    this.setupWebSocket();
  }
  
  setupWebSocket() {
    this.ws.onopen = () => {
      console.log("✅ Connecté");
      this.startWebRTC();
    };
    
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };
    
    this.ws.onclose = () => {
      console.log("❌ Déconnecté");
      this.cleanup();
    };
  }
  
  // ── Envoi de messages ──────────────────────────────────────
  
  send(type, data = {}) {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, ...data }));
    }
  }
  
  // Envoyer sa localisation
  sendLocation(latitude, longitude) {
    this.send("client_location", { latitude, longitude });
  }
  
  // Mettre à jour une livraison
  sendDeliveryUpdate(packageId, status) {
    this.send("delivery_update", { package_id: packageId, status });
  }
  
  // ── Réception de messages ──────────────────────────────────
  
  handleMessage(message) {
    const { type } = message;
    
    if (type === "notification") {
      this.handleNotification(message.notification_type, message.data);
    } else if (type === "answer") {
      this.handleWebRTCAnswer(message.sdp);
    } else if (type === "transcript") {
      console.log("📝 Transcription:", message.text);
    }
    // ... autres types
  }
  
  handleNotification(notificationType, data) {
    console.log("🔔 Notification:", notificationType, data);
    // Traiter la notification
  }
  
  // ── WebRTC ─────────────────────────────────────────────────
  
  async startWebRTC() {
    this.pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
    });
    
    // Ajouter la track audio
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => {
      this.pc.addTrack(track, stream);
    });
    
    // Gérer les candidats ICE
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        this.send("ice", {
          candidate: {
            candidate: event.candidate.candidate,
            sdpMid: event.candidate.sdpMid,
            sdpMLineIndex: event.candidate.sdpMLineIndex
          }
        });
      }
    };
    
    // Créer et envoyer l'offre
    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);
    
    this.send("offer", { sdp: offer.sdp });
  }
  
  async handleWebRTCAnswer(sdp) {
    const answer = new RTCSessionDescription({ type: "answer", sdp });
    await this.pc.setRemoteDescription(answer);
  }
  
  // ── Nettoyage ──────────────────────────────────────────────
  
  cleanup() {
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }
  }
}

// ── Utilisation ──────────────────────────────────────────────

const client = new VoiceClient("ws://localhost:8000/ws");

// Envoyer une notification après connexion
setTimeout(() => {
  client.sendLocation(48.8566, 2.3522);
  client.sendDeliveryUpdate("PKG-123", "in_progress");
}, 2000);
```

---

## 🌐 5. API HTTP pour Notifications

### Envoyer une notification à un client spécifique

```bash
curl -X POST "http://localhost:8000/notifications/send/{client_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "notification_type": "new_delivery",
    "data": {
      "package_id": "PKG-123",
      "address": "123 Main Street"
    }
  }'
```

**Réponse :**
```json
{
  "sent": true,
  "message": "Notification sent"
}
```

---

### Broadcast à tous les clients

```bash
curl -X POST "http://localhost:8000/notifications/broadcast" \
  -H "Content-Type: application/json" \
  -d '{
    "notification_type": "system_update",
    "data": {
      "message": "Maintenance dans 5 minutes"
    }
  }'
```

**Réponse :**
```json
{
  "sent": true,
  "count": 5
}
```

---

## 📊 6. Tableau Récapitulatif

### Messages Client → Serveur

| Type | Usage | Données |
|------|-------|---------|
| `offer` | WebRTC SDP offer | `{ sdp: "..." }` |
| `ice` | WebRTC ICE candidate | `{ candidate: {...} }` |
| `start` | Démarrer session WebRTC | `{}` |
| `stop` | Arrêter session WebRTC | `{}` |
| `test_tts` | Test synthèse vocale | `{ text: "..." }` |
| `client_location` | Envoyer position | `{ latitude, longitude }` |
| `delivery_update` | MAJ livraison | `{ package_id, status }` |
| *custom* | Message personnalisé | `{ ... }` |

---

### Messages Serveur → Client

| Type | Usage | Données |
|------|-------|---------|
| `answer` | WebRTC SDP answer | `{ sdp: "..." }` |
| `ice` | WebRTC ICE candidate | `{ candidate: {...} }` |
| `transcript` | Transcription STT | `{ text: "..." }` |
| `response` | Réponse LLM | `{ text: "..." }` |
| `intent` | Intention détectée | `{ intent: "..." }` |
| `notification` | Notification | `{ notification_type, data }` |
| `vad` | État VAD | `{ event, p }` |
| `interruption_decision` | Décision interruption | `{ decision, elapsed_ms, text }` |
| `interrupted` | TTS interrompu | `{}` |
| `tts_stop_now` | Arrêt TTS immédiat | `{}` |
| `error` | Erreur | `{ message }` |

---

## 🔧 7. Exemple d'Application React

```jsx
import { useEffect, useRef, useState } from "react";

function VoiceApp() {
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [notifications, setNotifications] = useState([]);
  
  useEffect(() => {
    // Connexion WebSocket
    wsRef.current = new WebSocket("ws://localhost:8000/ws");
    
    wsRef.current.onopen = () => {
      setConnected(true);
      console.log("✅ Connecté");
    };
    
    wsRef.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === "notification") {
        setNotifications(prev => [...prev, {
          type: message.notification_type,
          data: message.data,
          timestamp: new Date()
        }]);
      }
    };
    
    wsRef.current.onclose = () => {
      setConnected(false);
      console.log("❌ Déconnecté");
    };
    
    return () => {
      wsRef.current?.close();
    };
  }, []);
  
  // Envoyer une notification
  const sendNotification = (type, data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type,
        ...data
      }));
    }
  };
  
  return (
    <div>
      <h1>Voice App</h1>
      <p>Statut: {connected ? "✅ Connecté" : "❌ Déconnecté"}</p>
      
      <button onClick={() => sendNotification("client_location", {
        latitude: 48.8566,
        longitude: 2.3522
      })}>
        Envoyer ma position
      </button>
      
      <h2>Notifications reçues :</h2>
      <ul>
        {notifications.map((n, i) => (
          <li key={i}>
            {n.type}: {JSON.stringify(n.data)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default VoiceApp;
```

---

## 📱 8. Exemple d'Application Mobile (React Native)

```jsx
import React, { useEffect, useRef } from 'react';
import { WebSocket } from 'react-native';

const NotificationClient = () => {
  const ws = useRef(null);
  
  useEffect(() => {
    // Connexion
    ws.current = new WebSocket('ws://localhost:8000/ws');
    
    ws.current.onopen = () => {
      console.log('✅ Connecté');
      
      // Envoyer un message après connexion
      ws.current.send(JSON.stringify({
        type: 'client_location',
        latitude: 48.8566,
        longitude: 2.3522
      }));
    };
    
    ws.current.onmessage = (e) => {
      const message = JSON.parse(e.data);
      
      if (message.type === 'notification') {
        console.log('🔔 Notification reçue:', message);
        // Afficher une notification push
        showPushNotification(message.notification_type, message.data);
      }
    };
    
    ws.current.onclose = () => {
      console.log('❌ Déconnecté');
    };
    
    return () => {
      ws.current?.close();
    };
  }, []);
  
  return null;
};

export default NotificationClient;
```

---

## 🛠️ Dépannage

| Problème | Solution |
|----------|----------|
| Connexion refusée | Vérifier que le serveur tourne sur `ws://localhost:8000/ws` |
| Messages non reçus | Vérifier le handler `onmessage` et le parsing JSON |
| Déconnexions fréquentes | Implémenter un reconnexion automatique avec backoff |
| Notifications non reçues | Vérifier que le `client_id` est correct dans l'API HTTP |

---

## 📚 Ressources

- [WebSocket API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [WebRTC API](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
- [aiortc Documentation](https://aiortc.readthedocs.io/)

---

**Dernière mise à jour :** 2026-03-31
