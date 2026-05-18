"""
Trip - Modèle de données représentant une destination de livraison

Cette classe encapsule toutes les informations nécessaires pour gérer une livraison,
créée automatiquement à partir des données d'un Package.

Données Obligatoires:
    - id : ID du package associé (pas d'auto-génération)
    - name : Adresse de livraison (depuis le package)
    - latitude : Coordonnée GPS (depuis l'adresse associée)
    - longitude : Coordonnée GPS (depuis l'adresse associée)

Métadonnées Flotte (Optionnelles):
    - client_name : Nom du client destinataire (depuis le package)
    - package_info : Description du colis (depuis le package)
    - delivery_status : État de livraison (depuis le status du package)

Note:
    Un Trip est lié à un Package. Utilisez Trip.from_package() pour créer
    une instance à partir d'un package et de son adresse associée.

Exemple:
    >>> trip = Trip.from_package(package, address)
    >>> json_data = trip.to_dict()  # → sauvegarder en fichier
    >>> restored = Trip.from_dict(json_data)  # → charger depuis fichier
"""

import json
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .package import Package
    from .address import Address


@dataclass
class Trip:
    """
    Classe représentant une destination de livraison créée depuis un Package.
    
    Attributes:
        id: ID du package associé (identifiant unique)
        name: Adresse de livraison
        latitude: Latitude GPS (WGS84) - depuis l'adresse associée
        longitude: Longitude GPS (WGS84) - depuis l'adresse associée
        client_name: Nom du client destinataire
        package_info: Description du colis
        delivery_status: État de livraison (depuis le status du package)
    """
    
    # Champs obligatoires
    id: str
    name: str
    latitude: float
    longitude: float
    
    # Champs optionnels avec valeurs par défaut
    client_name: Optional[str] = None
    package_info: Optional[str] = None
    delivery_status: Optional[str] = None
    
    # ===== MÉTHODES D'ACCÈS (GETTERS) =====
    
    def get_id(self) -> str:
        """Retourne l'ID du package associé."""
        return self.id
    
    def get_name(self) -> str:
        """Retourne l'adresse de livraison."""
        return self.name
    
    def get_latitude(self) -> float:
        """Retourne la latitude GPS en coordonnées WGS84."""
        return self.latitude
    
    def get_longitude(self) -> float:
        """Retourne la longitude GPS en coordonnées WGS84."""
        return self.longitude
    
    def get_client_name(self) -> Optional[str]:
        """Retourne le nom du client destinataire."""
        return self.client_name
    
    def get_package_info(self) -> Optional[str]:
        """Retourne la description du colis."""
        return self.package_info
    
    def get_delivery_status(self) -> Optional[str]:
        """
        Retourne l'état de livraison selon le cycle de vie métier.
        
        Valeurs possibles:
            - in_stock : En stock
            - planned : Planifié
            - in_progress_delivery : En cours de livraison
            - delivered_successfully : Livré avec succès
            - delivery_failure : Échec de livraison
        """
        return self.delivery_status
    
    # ===== CRÉATION DEPUIS UN PACKAGE =====
    
    @classmethod
    def from_package(cls, package: "Package", address: Optional["Address"] = None) -> "Trip":
        """
        Crée un Trip à partir d'un Package et éventuellement de son adresse associée.
        
        Mapping des champs:
            - id ← package.id
            - name ← address.label (ou package.address_label, ou package.address)
            - latitude ← address.latitude (ou 0.0 si non fourni)
            - longitude ← address.longitude (ou 0.0 si non fourni)
            - client_name ← package.client_name
            - package_info ← package.description
            - delivery_status ← package.status.value
        
        Args:
            package: Instance du Package source
            address: Instance Address optionnelle pour les coordonnées GPS
            
        Returns:
            Nouvelle instance de Trip
        """
        # Déterminer le nom (adresse) - priorité: address.label > address_label > address
        name = address.label if address else (package.address_label or package.address)
        
        # Déterminer les coordonnées GPS
        latitude = address.latitude if address else 0.0
        longitude = address.longitude if address else 0.0
        
        # Mapper le status du package
        delivery_status = package.status.value if package.status else None
        
        return cls(
            id=package.id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            client_name=package.client_name,
            package_info=package.description,
            delivery_status=delivery_status,
        )
    
    # ===== SÉRIALISATION JSON =====
    
    def to_dict(self) -> dict:
        """
        Convertit ce Trip en dictionnaire pour persistance/API.
        
        Les champs None ne sont pas inclus dans le dictionnaire.
        
        Returns:
            Dictionnaire avec toutes les données
            
        Exemple:
            {
                "id": "69c59d30fb98e15a3cf534bc",
                "name": "Cité El Khadra, Tunis",
                "latitude": 36.8276,
                "longitude": 10.1950,
                "clientName": "Jean Dupont",
                "packageInfo": "Boîte 5kg",
                "deliveryStatus": "planned"
            }
        """
        data = {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }
        
        if self.client_name is not None:
            data["clientName"] = self.client_name
        if self.package_info is not None:
            data["packageInfo"] = self.package_info
        if self.delivery_status is not None:
            data["deliveryStatus"] = self.delivery_status
        
        return data
    
    def to_json(self) -> str:
        """
        Convertit ce Trip en chaîne JSON.
        
        Returns:
            Chaîne JSON avec toutes les données
        """
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: dict) -> "Trip":
        """
        Crée un Trip à partir d'un dictionnaire.
        
        Args:
            data: Dictionnaire contenant les données du Trip
            
        Returns:
            Nouvelle instance de Trip
            
        Raises:
            ValueError: Si champs obligatoires manquants
            
        Note:
            Les champs "id", "name", "latitude", "longitude" sont obligatoires.
        """
        # Validation des champs obligatoires
        required_fields = ["id", "name", "latitude", "longitude"]
        for field_name in required_fields:
            if field_name not in data:
                raise ValueError(f"Champ obligatoire manquant: {field_name}")
        
        return cls(
            id=data["id"],
            name=data["name"],
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            client_name=data.get("clientName"),
            package_info=data.get("packageInfo"),
            delivery_status=data.get("deliveryStatus"),
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "Trip":
        """
        Crée un Trip à partir d'une chaîne JSON.
        
        Args:
            json_str: Chaîne JSON contenant les données
            
        Returns:
            Nouvelle instance de Trip
            
        Raises:
            json.JSONDecodeError: Si le JSON est invalide
            ValueError: Si champs obligatoires manquants
        """
        data = json.loads(json_str)
        return cls.from_dict(data)
    
    # ===== MÉTHODES STANDARDS =====
    
    def __eq__(self, other: object) -> bool:
        """
        Compare deux Trip par leur ID unique.
        
        Deux Trip sont considérées égales si elles ont le même ID.
        """
        if not isinstance(other, Trip):
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        """Retourne le hash basé sur l'ID unique."""
        return hash(self.id)
    
    def __str__(self) -> str:
        """
        Retourne une représentation textuelle pour débogage.
        
        Format: Trip{id='...', name='...', lat=..., lng=..., ...}
        """
        parts = [
            f"id='{self.id}'",
            f"name='{self.name}'",
            f"lat={self.latitude}",
            f"lng={self.longitude}",
        ]
        
        if self.client_name:
            parts.append(f"client='{self.client_name}'")
        if self.delivery_status:
            parts.append(f"status='{self.delivery_status}'")
        
        return f"Trip{{{', '.join(parts)}}}"
    
    # ===== MÉTHODES UTILITAIRES =====
    
    def copy(
        self,
        name: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        client_name: Optional[str] = None,
        package_info: Optional[str] = None,
        delivery_status: Optional[str] = None,
    ) -> "Trip":
        """
        Crée une copie de ce Trip avec des modifications optionnelles.
        
        Args:
            name: Nouvelle adresse (ou None pour garder l'actuel)
            latitude: Nouvelle latitude (ou None)
            longitude: Nouvelle longitude (ou None)
            client_name: Nouveau nom client (ou None)
            package_info: Nouvelle description (ou None)
            delivery_status: Nouvel état de livraison (ou None)
            
        Returns:
            Nouvelle instance de Trip avec les modifications appliquées
        """
        return Trip(
            id=self.id,
            name=name if name is not None else self.name,
            latitude=latitude if latitude is not None else self.latitude,
            longitude=longitude if longitude is not None else self.longitude,
            client_name=client_name if client_name is not None else self.client_name,
            package_info=package_info if package_info is not None else self.package_info,
            delivery_status=delivery_status if delivery_status is not None else self.delivery_status,
        )
