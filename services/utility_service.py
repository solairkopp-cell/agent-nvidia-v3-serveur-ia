import json
from typing import Dict, Any, List, Optional


class UtilityService:
    _instance = None
    # Correction : l'ID doit être un str si tes IDs contiennent des lettres
    current_trip_id: Optional[str] = None
    trip_order: List[str] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data_cache = {}
            cls._instance.trip_order = []
            cls._instance.current_trip_id = None
        return cls._instance

    def set_next_trip(self) -> str:
        if not self.trip_order:
            return "empty data cache, no trips available"

        if self.current_trip_id is None:
            self.current_trip_id = self.trip_order[0]
            return f"New trip: {self.current_trip_id} set"

        try:
            current_index = self.trip_order.index(self.current_trip_id)
        except ValueError:
            self.current_trip_id = self.trip_order[0]
            return f"New trip: {self.current_trip_id} set"

        if current_index >= len(self.trip_order) - 1:
            self.current_trip_id = None
            return "No more trips, all deliveries done"

        self.current_trip_id = self.trip_order[current_index + 1]
        return f"New trip: {self.current_trip_id} set"

    def get_delivery_info(self, target_id: str) -> str:
        item = self._data_cache.get(str(target_id))
        if item:
            return f"delivery for {item.get('clientName')}"
        return "Delivery not found"

    def get_delivery(self, target_id: str) -> Optional[Dict[str, Any]]:
        """Retourne l'objet brut. C'est la méthode la plus rapide."""
        return self._data_cache.get(str(target_id))

    def get_all_deliveries(self) -> List[Dict[str, Any]]:
        """Retourne la liste de tous les objets de livraison bruts."""
        return [self._data_cache[trip_id] for trip_id in self.trip_order if trip_id in self._data_cache]

    def get_deliveries_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "clientName": self._data_cache[trip_id].get("clientName"),
                "address": self._data_cache[trip_id].get("address"),
                "packageInfo": self._data_cache[trip_id].get("packageInfo"),
            }
            for trip_id in self.trip_order
            if trip_id in self._data_cache
        ]

    def get_current_delivery_info(self) -> str:
        # Utilise l'ID actuellement stocké dans l'instance
        if self.current_trip_id is None:
            return "No current delivery set"
        return self.get_delivery_info(self.current_trip_id)

    def get_next_delivery_info(self) -> str:
        """Renvoie les infos du prochain trajet sans changer l'état actuel."""
        if not self.trip_order or self.current_trip_id is None:
            return "Indisponible"

        try:
            current_index = self.trip_order.index(self.current_trip_id)
        except ValueError:
            return "Erreur lors de la récupération"

        next_index = current_index + 1
        if next_index >= len(self.trip_order):
            return "Indisponible"

        return self.get_delivery_info(self.trip_order[next_index])

    def get_next_delivery(self) -> Optional[Dict[str, Any]]:
        """Retourne l'objet brut du prochain trajet sans changer l'état actuel.
        Retourne None si on est sur la dernière livraison ou si aucune livraison n'est disponible."""
        if not self.trip_order or self.current_trip_id is None:
            return None

        try:
            current_index = self.trip_order.index(self.current_trip_id)
        except ValueError:
            return None

        next_index = current_index + 1
        if next_index >= len(self.trip_order):
            return None
        return self.get_delivery(self.trip_order[next_index])

    def is_last_trip(self) -> bool:
        """Vérifie si le trajet actuel est le dernier de la liste."""
        if not self.trip_order:
            return True

        if self.current_trip_id is None:
            return False

        try:
            return self.trip_order.index(self.current_trip_id) == len(self.trip_order) - 1
        except ValueError:
            return False

    def remove_trip(self, trip_id: str) -> None:
        trip_id = str(trip_id)
        if trip_id in self._data_cache:
            self._data_cache.pop(trip_id, None)

        if trip_id not in self.trip_order:
            return

        removed_index = self.trip_order.index(trip_id)
        self.trip_order.remove(trip_id)

        if self.current_trip_id == trip_id:
            if removed_index >= len(self.trip_order):
                self.current_trip_id = None
            else:
                self.current_trip_id = self.trip_order[removed_index]

    def load_from_trips(self, trips_data: list[dict]) -> None:
        self._data_cache = {str(item["id"]): item for item in trips_data}
        self.trip_order = [str(item["id"]) for item in trips_data]
        self.current_trip_id = self.trip_order[0] if self.trip_order else None