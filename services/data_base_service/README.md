# Data Base Service - Python

Service Python pour l'interface d'administration Rytle Dashboard (Fleet Management).

## 📁 Architecture

```
data_base_service/
├── entities/
│   ├── __init__.py
│   ├── enum/
│   │   ├── __init__.py
│   │   ├── package_status.py    # Enum PackageStatus
│   │   └── dispatch_step.py     # Enum DispatchStep
│   └── models/
│       ├── __init__.py
│       ├── address.py
│       ├── administrator.py
│       ├── delivery_failure.py
│       ├── driver.py
│       ├── driver_availability.py
│       ├── package.py
│       ├── schedule.py
│       ├── schedule_package.py
│       ├── trip.py              # Modèle Trip (créé depuis Package)
│       ├── unattended_drop_off.py
│       └── vehicle.py
├── service/
│   ├── __init__.py
│   ├── http_request_services.py  # HTTP client async
│   ├── crud_service.py           # CRUD operations
│   ├── token_manager.py          # Gestion du token (cache 24h)
│   ├── logger_service.py         # Logging dans cli.log
│   └── planning_service.py       # Service métier (3 fonctions essentielles)
├── cli.py                        # ⚠️ CLI historique (déprécié)
├── planning_cli.py               # ✅ CLI interactif recommandé
├── update_package_status_cli.py  # CLI de mise à jour standalone
├── requirements.txt
├── token_cache.md                # Cache du token (auto-généré)
└── cli.log                       # Logs des opérations
```

## 📦 Entités

| Entité | Champs | Entity ID |
|--------|--------|-----------|
| Driver | id, serial_number, name | `69bd744efb98e15a3cf53374` |
| Administrator | id, serial_number, name | `69bd7351fb98e15a3cf53373` |
| Vehicle | id, license_plate, brand, weight_capacity, volume_capacity | `69bd75dffb98e15a3cf53375` |
| Package | id, client_name, address, address_label, weight, volume, description, delivery_date, is_fragile, status | `69bd7ac1fb98e15a3cf53376` |
| Schedule | id, delivery_date, driver_serial_number, vehicle_license_plate | `69bd7d09fb98e15a3cf53377` |
| DriverAvailability | id, driver_id, available_date | `69bd7dfdfb98e15a3cf53378` |
| SchedulePackage | id, schedule_id, package_id, position | `69bd7ee9fb98e15a3cf53379` |
| DeliveryFailure | id, package_id, cause, comment | `69bd7f7cfb98e15a3cf5337a` |
| UnattendedDropOff | id, package_id, drop_off_location, photo_path | `69bd80b5fb98e15a3cf5337b` |
| Address | id, label, latitude, longitude | `69c06c22fb98e15a3cf533a5` |
| Trip | id (package.id), name, latitude, longitude, client_name, package_info, delivery_status | (créé depuis Package) |

## 🚀 Installation

```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

Le token d'authentification est géré automatiquement :
- **Première utilisation** : connexion API → token sauvegardé dans `token_cache.md`
- **Validité** : 24 heures
- **Renouvellement** : automatique après expiration

---

## 🔧 Planning Service

Le module `planning_service.py` fournit un service minimaliste et efficace pour la gestion des livraisons.

### Trois fonctions essentielles

| Fonction | Description |
|----------|-------------|
| `get_delivery_trips()` | Récupère les trips ordonnés + export JSON automatique |
| `update_package_status()` | Met à jour le statut d'un package |
| `add_delivery_failure()` | Ajoute un échec de livraison |

---

### Mode 1 : Via la classe `PlanningService` (Recommandé pour plusieurs appels)

```python
from service import PlanningService
from entities.enum.package_status import PackageStatus

# Initialiser le service
service = PlanningService()

try:
    # 1. Récupérer les trips (export JSON automatique)
    trips = await service.get_delivery_trips("000")
    
    # Les trips sont déjà :
    # - Triés par position
    # - Avec adresses remplies (lat/lng)
    # - Filtrés (uniquement 'planned')
    # - Exportés en JSON (delivery_trips_2026-03-31.json)
    
    for i, trip in enumerate(trips, 1):
        print(f"{i}. {trip.get_name()} - {trip.get_delivery_status()}")
    
    # 2. Mettre à jour un package
    await service.update_package_status(
        "69c59d30fb98e15a3cf534bc",
        PackageStatus.DELIVERED_SUCCESSFULLY
    )
    
    # 3. Ajouter un échec de livraison
    await service.add_delivery_failure(
        "69c59d31fb98e15a3cf534bd",
        cause=1,  # Destinataire absent
        comment="Client n'était pas à l'adresse indiquée"
    )
    
finally:
    # Important : fermer la session HTTP
    await service.close()
```

**Avantages :**
- ✅ Session HTTP réutilisée (plus rapide pour plusieurs appels)
- ✅ Code plus propre pour les opérations multiples

**Inconvénient :**
- ⚠️ Penser à appeler `await service.close()` à la fin

---

### Mode 2 : Via les fonctions utilitaires (Simple pour un appel unique)

```python
from service import get_delivery_trips, update_package, add_delivery_failure
from entities.enum.package_status import PackageStatus

# Un seul appel - pas besoin de gérer close()
trips = await get_delivery_trips("000")

# Mettre à jour un package
await update_package("69c59d30...", PackageStatus.DELIVERED_SUCCESSFULLY)

# Ajouter un échec de livraison
await add_delivery_failure("69c59d30...", cause=1, comment="Client absent")
```

**Avantages :**
- ✅ Ultra-simple
- ✅ Pas de `close()` à gérer

**Inconvénient :**
- ⚠️ Nouvelle session HTTP à chaque appel (moins efficace pour plusieurs appels)

---

### Quel mode choisir ?

| Situation | Mode recommandé |
|-----------|-----------------|
| Plusieurs appels (ex: get + update + add) | **Classe `PlanningService`** |
| Un seul appel (ex: juste get) | **Fonctions utilitaires** |
| CLI interactif | **Classe `PlanningService`** |
| Script rapide | **Fonctions utilitaires** |

---

## 🗺️ Trips et Export JSON

### Qu'est-ce qu'un Trip ?

Un **Trip** représente une destination de livraison créée automatiquement depuis un **Package**.

| Champ Trip | Source |
|------------|--------|
| `id` | `package.id` |
| `name` | Adresse de livraison (ou `address.label`) |
| `latitude` | `address.latitude` |
| `longitude` | `address.longitude` |
| `client_name` | `package.client_name` |
| `package_info` | `package.description` |
| `delivery_status` | `package.status.value` |

### Création automatique

```python
from service import get_delivery_trips

# Un seul appel suffit !
trips = await get_delivery_trips("000")

# Ce qui est fait automatiquement :
# 1. ✅ Récupération du driver par serial number
# 2. ✅ Récupération des schedules pour aujourd'hui
# 3. ✅ Récupération des SchedulePackage et tri par 'position'
# 4. ✅ Filtrage des packages (uniquement 'planned')
# 5. ✅ Récupération des adresses associées
# 6. ✅ Création des objets Trip avec tous les champs remplis
# 7. ✅ Export automatique en JSON (delivery_trips_2026-03-31.json)
```

### Format du fichier JSON

```json
[
  {
    "id": "69c59d30fb98e15a3cf534bc",
    "name": "Cité El Khadra, Tunis",
    "latitude": 36.8276,
    "longitude": 10.1950,
    "clientName": "Jean Dupont",
    "packageInfo": "Boîte 5kg - Fragile",
    "deliveryStatus": "planned"
  },
  {
    "id": "69c59d31fb98e15a3cf534bd",
    "name": "Avenue Habib Bourguiba",
    "latitude": 36.8000,
    "longitude": 10.1800,
    "clientName": "Marie Martin",
    "packageInfo": "Documents urgents",
    "deliveryStatus": "planned"
  }
]
```

Les trips sont **automatiquement ordonnés** selon le champ `position` de `SchedulePackage`.

### Options d'export

```python
# Avec export JSON (défaut)
trips = await get_delivery_trips("000")
# → Fichier: delivery_trips_2026-03-31.json

# Sans export JSON
trips = await get_delivery_trips("000", export_json=False)

# Avec fichier personnalisé
trips = await get_delivery_trips("000", output_file="mes_livraisons.json")

# Pour une date spécifique
trips = await get_delivery_trips("000", date="2026-03-31")
```

---

## 💻 CLI - Interface interactive (Recommandé)

```bash
python planning_cli.py
```

### Fonctionnement

1. Demande le numéro de série du driver
2. Récupère les trips pour la date actuelle (packages `planned` uniquement)
3. Affiche la liste des tournées et packages
4. Menu interactif :
   - **1** : Mettre à jour le statut d'un package
   - **2** : Signaler un échec de livraison
   - **3** : Actualiser les données
   - **0** : Quitter

### Exemple de sortie

```
======================================================================
🚚 RYDLE DASHBOARD - Gestion des livraisons
======================================================================

Entrez votre numéro de série driver: 000

📦 Récupération des livraisons...
✅ 15 trip(s) créé(s) et ordonné(s) par position
✅ 15 trip(s) exporté(s) vers delivery_trips_2026-03-31.json

======================================================================
📋 LIVRAISONS - 2026-03-31
======================================================================

🚛 Tournée #1
   Véhicule: 69c59d01fb98e15a3cf534ba
   Nombre de colis: 3

   1. [planned] Client A 🧊
      📍 Cité El Khadra, Tunis
      📦 2.5kg / 0.3m³

   2. [planned] Client B
      📍 Avenue Habib Bourguiba
      📦 1.0kg / 0.1m³

======================================================================
📊 Total: 1 tournée(s), 3 colis à livrer
======================================================================

Options:
  [1] 🔄 Mettre à jour le statut d'un package
  [2] ❌ Signaler un échec de livraison
  [3] 🔄 Actualiser les données
  [0] ❌ Quitter

Votre choix:
```

### Signaler un échec de livraison

Lorsque vous sélectionnez l'option **2**, le CLI vous guide pour :

1. Choisir un package parmi la liste
2. Sélectionner la cause de l'échec (1 à 6) :
   - **1** : Destinataire absent
   - **2** : Adresse incorrecte
   - **3** : Colis endommagé
   - **4** : Refus du destinataire
   - **5** : Accès impossible
   - **6** : Autre
3. Saisir un commentaire décrivant l'échec
4. Confirmer le signalement

Après confirmation :
- L'échec de livraison est enregistré dans l'API
- Le statut du package est automatiquement mis à jour en `delivery_failure`
- La liste des livraisons est actualisée (le package n'apparaît plus car il n'est plus `planned`)

---

## 🔄 CLI - Mettre à jour le statut d'un package (Standalone)

```bash
python update_package_status_cli.py
```

### Fonctionnement

1. Authentification automatique
2. Récupération **uniquement des packages avec le statut `planned`**
3. Affichage de la liste (client + adresse + statut actuel)
4. Sélection du package à modifier
5. Choix du nouveau statut parmi :
   - 📥 `in_stock`
   - 📋 `planned` (statut actuel - peut être reconfirmé)
   - 🚚 `in_progress_delivery`
   - ✅ `delivered_successfully`
   - ❌ `delivery_failure`
6. Confirmation et mise à jour

### Optimisation

Le CLI filtre les packages **avant** de les enrichir avec les adresses :
- Seuls les packages `planned` sont récupérés de l'API
- L'enrichissement des adresses est fait uniquement sur les packages filtrés
- Réduction de la consommation mémoire et des appels API inutiles

---

## 📜 CLI Historique (Déprécié)

```bash
python cli.py
```

> ⚠️ **Ce CLI est déprécié** - Utilisez `planning_cli.py` à la place.

Fonctionne toujours mais sera supprimé dans une future version.

---

## 🌐 API Utilisées

### Base URL
```
https://v2.fleet.akkurad-engineering.com/api/
```

### Endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/auth/login` | POST | Authentification |
| `/entity-instances/entity/{entityId}` | GET | Récupérer toutes les instances |
| `/entity-instances/{id}` | GET | Récupérer par ID |
| `/entity-instances/by-reference/{referenceId}` | GET | Récupérer par référence |
| `/entity-instances/entity/{entityId}/search?query={query}` | GET | Rechercher |
| `/entity-instances/entity/{entityId}` | POST | Créer |
| `/entity-instances/{id}` | PUT | Mettre à jour |
| `/entity-instances/{id}` | DELETE | Supprimer |

---

## 📝 Logs

Toutes les opérations sont journalisées dans `cli.log` :

```
2026-03-31 00:28:30 - INFO - Récupération des trips pour le driver: 000
2026-03-31 00:28:30 - INFO - ✅ SUCCÈS: Driver trouvé: vivien (serial: 000, ID: 69c59d19fb98e15a3cf534bb)
2026-03-31 00:28:30 - INFO - ✅ SUCCÈS: 15 trip(s) créé(s) et ordonné(s) par position
2026-03-31 00:28:30 - INFO - ✅ SUCCÈS: 15 trip(s) exporté(s) vers delivery_trips_2026-03-31.json
```

---

## 🔍 Notes techniques

### Structure des réponses API

Toutes les réponses de l'API ont cette structure :

```json
{
  "id": "69c59d19fb98e15a3cf534bb",
  "entityId": "69bd744efb98e15a3cf53374",
  "data": {
    "serial_number": "000",
    "name": "vivien"
  },
  "createdAt": "2026-03-26T20:54:49.207",
  "updatedAt": "2026-03-26T20:54:49.207",
  "createdBy": "n.baldi22412@pi.tn",
  "deleted": false
}
```

> ⚠️ **Les données réelles sont toujours dans le champ `data`**

### Champs avec underscore

Contrairement à la convention camelCase, l'API utilise des champs avec underscore :

| Champ API | Convention attendue |
|-----------|---------------------|
| `serial_number` | ~~serialNumber~~ |
| `driver_serial_number` | ~~driverSerialNumber~~ |
| `license_plate` | ~~licensePlate~~ |
| `weight_capacity` | ~~weightCapacity~~ |
| `volume_capacity` | ~~volumeCapacity~~ |
| `delivery_date` | ~~deliveryDate~~ |
| `available_date` | ~~availableDate~~ |
| `schedule_id` | ~~scheduleId~~ |
| `package_id` | ~~packageId~~ |
| `driver_id` | ~~driverId~~ |
| `vehicle_license_plate` | ~~vehicleLicensePlate~~ |

### Endpoint by-reference

L'endpoint `/entity-instances/by-reference/{referenceId}` retourne **toutes** les entités liées à un ID (driver, schedule, package, etc.). 

**Important** : Il faut filtrer par `entityId` pour obtenir le type désiré.

Exemple :
```python
# Retourne toutes les entités liées au driver
all_entities = await http.get_json(f"entity-instances/by-reference/{driver_id}")

# Filtrer pour ne garder que les schedules
schedules = [e for e in all_entities if e.get("entityId") == EntityIds.SCHEDULE]
```

### Enrichissement des adresses

Le champ `address` d'un package est une **référence** vers l'entité ADDRESS. Le service enrichit automatiquement les packages avec le label d'adresse :

```python
# Le package contient :
package.address = "69c403b1fb98e15a3cf53418"  # ID de l'adresse
package.address_label = "Cité El Khadra, Tunis"  # Label enrichi
```

### Trips ordonnés par position

Les trips sont automatiquement triés selon le champ `position` de `SchedulePackage` :

```python
# Les SchedulePackage sont triés par position
all_schedule_packages.sort(key=lambda sp: sp.position if sp.position is not None else float('inf'))

# Puis convertis en Trip
trips = [Trip.from_package(package, address) for sp in all_schedule_packages]
```

---

## 📋 TODO

- [ ] Ajouter des tests unitaires
- [ ] Gérer les erreurs réseau (retry avec backoff)
- [ ] Export des livraisons en CSV
- [ ] Pagination pour les grandes listes de packages
- [ ] Cache des packages pour éviter les requêtes répétées

---

## 📄 Licence

Projet interne - Rytle Dashboard
