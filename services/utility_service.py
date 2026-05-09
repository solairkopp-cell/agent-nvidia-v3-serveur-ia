import json
from typing import Dict, Any, List, Optional



class UtilityService:
    _instance = None
    # Correction : l'ID doit être un str si tes IDs contiennent des lettres
    current_trip_id: Optional[str] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data_cache = {}
            cls._instance.current_trip_id = None
            cls._instance._load_data()
        return cls._instance

    def _load_data(self) -> None:
        from pathlib import Path
        path = Path(__file__).parent.parent / "data.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)

            # Mise en cache avec ID comme clé (string)
            self._data_cache = {
                str(item["id"]): item 
                for item in raw_list
            }
            if self._data_cache:
                self.current_trip_id = list(self._data_cache.keys())[0]

        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            print(f"Erreur chargement data: {e}")
            self._data_cache = {}
    
    def set_next_trip(self) -> str:
        if not self._data_cache:
            return "empty data cache, no trips available"

        ids = list(self._data_cache.keys())

        if self.current_trip_id is None:
            self.current_trip_id = ids[0]
            return f"New trip: {self.current_trip_id} set"

        try:
            current_index = ids.index(self.current_trip_id)
            if current_index >= len(ids) - 1:
                self.current_trip_id = None
                return "No more trips, all deliveries done"
            self.current_trip_id = ids[current_index + 1]
        except (ValueError, KeyError):
            self.current_trip_id = ids[0]

        return f"New trip: {self.current_trip_id} set"
    
    def get_delivery_info(self, target_id: str) -> str:
        item = self._data_cache.get(target_id)
        if item:
            return f"delivery for {item.get('clientName')}"
        return "Delivery not found"
    
    def get_delivery(self, target_id: str) -> Optional[Dict[str, Any]]:
        """Retourne l'objet brut. C'est la méthode la plus rapide."""
        return self._data_cache.get(target_id)

    def get_deliveries_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "clientName": d.get("clientName"),
                "address": d.get("address"),
                "packageInfo": d.get("packageInfo")
            }
            for d in self._data_cache.values()
        ]

    def get_current_delivery_info(self) -> str:
        # Utilise l'ID actuellement stocké dans l'instance
        if self.current_trip_id is None:
            return "No current delivery set"
        return self.get_delivery_info(self.current_trip_id)
    
    def get_next_delivery_info(self) -> str:
        """Renvoie les infos du prochain trajet sans changer l'état actuel."""
        if not self._data_cache or self.current_trip_id is None:
            return "Indisponible"

        ids = list(self._data_cache.keys())
        
        try:
            current_index = ids.index(self.current_trip_id)
            next_index = (current_index + 1) % len(ids)
            next_id = ids[next_index]
            return self.get_delivery_info(next_id)
        except (ValueError, KeyError):
            return "Erreur lors de la récupération"
    
    def get_next_delivery(self) -> Optional[Dict[str, Any]]:
        """Retourne l'objet brut du prochain trajet sans changer l'état actuel.
        Retourne None si on est sur la dernière livraison ou si aucune livraison n'est disponible."""
        if not self._data_cache or self.current_trip_id is None:
            return None

        ids = list(self._data_cache.keys())
        try:
            current_index = ids.index(self.current_trip_id)
            next_index = current_index + 1
            if next_index >= len(ids):
                return None  # Pas de prochain trajet, on est au dernier
            return self.get_delivery(ids[next_index])
        except (ValueError, KeyError):
            return None
        
    def is_last_trip(self) -> bool:
        """Vérifie si le trajet actuel est le dernier de la liste.
        Retourne True aussi quand current_trip_id est None (toutes les livraisons sont terminées)."""
        if not self._data_cache:
            return False

        if self.current_trip_id is None:
            return True  # Plus aucun trip en cours → route terminée

        ids = list(self._data_cache.keys())
        try:
            return ids.index(self.current_trip_id) == len(ids) - 1
        except ValueError:
            return False