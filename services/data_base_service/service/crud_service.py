from typing import Optional, List
from datetime import datetime

from ..entities.models import (
    Address,
    Administrator,
    DeliveryFailure,
    Driver,
    DriverAvailability,
    Package,
    Schedule,
    SchedulePackage,
    UnattendedDropOff,
    Vehicle,
)
from ..entities.enum.package_status import PackageStatus
from .http_request_services import HttpRequestServices
from .logger_service import log_info, log_error, log_success, log_debug, log_warning


# Entity IDs from Flutter project
class EntityIds:
    DRIVER = "69bd744efb98e15a3cf53374"
    ADMINISTRATOR = "69bd7351fb98e15a3cf53373"
    VEHICLE = "69bd75dffb98e15a3cf53375"
    PACKAGE = "69bd7ac1fb98e15a3cf53376"
    SCHEDULE = "69bd7d09fb98e15a3cf53377"
    DRIVER_AVAILABILITY = "69bd7dfdfb98e15a3cf53378"
    SCHEDULE_PACKAGE = "69bd7ee9fb98e15a3cf53379"
    DELIVERY_FAILURE = "69bd7f7cfb98e15a3cf5337a"
    UNATTENDED_DROP_OFF = "69bd80b5fb98e15a3cf5337b"
    ADDRESS = "69c06c22fb98e15a3cf533a5"  # Entity ID pour ADDRESS


class CrudService:
    def __init__(self, http_service: HttpRequestServices):
        self.http = http_service

    # ==================== ADMINISTRATOR ====================

    async def get_all_administrator(self) -> List[Administrator]:
        log_info("Récupération de tous les administrators")
        data = await self.http.get_entity_instances(EntityIds.ADMINISTRATOR)
        result = [self._map_to_administrator(item) for item in (data or [])]
        log_success(f"{len(result)} administrator(s) récupéré(s)")
        return result

    async def get_administrator_by_id(self, id: str) -> Optional[Administrator]:
        log_info(f"Récupération de l'administrator par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Administrator trouvé: {id}")
            return self._map_to_administrator(data)
        log_error(f"Administrator non trouvé: {id}")
        return None

    async def add_administrator(self, admin: Administrator) -> Optional[str]:
        log_info(f"Création d'un nouvel administrator: {admin.serial_number}")
        data = self._administrator_to_dict(admin)
        result = await self.http.create_entity_instance(EntityIds.ADMINISTRATOR, data)
        if result:
            log_success(f"Administrator créé avec ID: {result}")
        else:
            log_error(f"Échec de la création de l'administrator: {admin.serial_number}")
        return result

    async def update_administrator(self, id: str, admin: Administrator) -> bool:
        log_info(f"Mise à jour de l'administrator: {id}")
        data = self._administrator_to_dict(admin)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Administrator {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour de l'administrator: {id}")
        return result

    async def delete_administrator(self, id: str) -> bool:
        log_info(f"Suppression de l'administrator: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Administrator {id} supprimé")
        else:
            log_error(f"Échec de la suppression de l'administrator: {id}")
        return result

    async def search_administrator(self, serial_number: str) -> Optional[Administrator]:
        log_info(f"Recherche de l'administrator par serial number: {serial_number}")
        data = await self.http.search(EntityIds.ADMINISTRATOR, serial_number)
        if data:
            log_success(f"Administrator trouvé: {serial_number}")
            return self._map_to_administrator(data[0])
        log_warning(f"Administrator non trouvé: {serial_number}")
        return None

    def _map_to_administrator(self, data: dict) -> Administrator:
        # Les données réelles sont dans le champ 'data' de la réponse API
        admin_data = data.get("data", data)
        return Administrator(
            id=data.get("id"),
            serial_number=admin_data.get("serial_number", ""),
            name=admin_data.get("name", ""),
        )

    def _administrator_to_dict(self, admin: Administrator) -> dict:
        return {
            "serial_number": admin.serial_number,
            "name": admin.name,
        }

    # ==================== DRIVER ====================

    async def get_all_driver(self) -> List[Driver]:
        log_info("Récupération de tous les drivers")
        data = await self.http.get_entity_instances(EntityIds.DRIVER)
        result = [self._map_to_driver(item) for item in (data or [])]
        log_success(f"{len(result)} driver(s) récupéré(s)")
        return result

    async def get_driver_by_id(self, id: str) -> Optional[Driver]:
        log_info(f"Récupération du driver par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Driver trouvé: {id}")
            return self._map_to_driver(data)
        log_error(f"Driver non trouvé: {id}")
        return None

    async def add_driver(self, driver: Driver) -> Optional[str]:
        log_info(f"Création d'un nouveau driver: {driver.serial_number}")
        data = self._driver_to_dict(driver)
        result = await self.http.create_entity_instance(EntityIds.DRIVER, data)
        if result:
            log_success(f"Driver créé avec ID: {result}")
        else:
            log_error(f"Échec de la création du driver: {driver.serial_number}")
        return result

    async def update_driver(self, id: str, driver: Driver) -> bool:
        log_info(f"Mise à jour du driver: {id}")
        data = self._driver_to_dict(driver)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Driver {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du driver: {id}")
        return result

    async def delete_driver(self, id: str) -> bool:
        log_info(f"Suppression du driver: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Driver {id} supprimé")
        else:
            log_error(f"Échec de la suppression du driver: {id}")
        return result

    async def search_driver(self, query: str) -> Optional[Driver]:
        """
        Recherche un driver par serial number.
        Utilise l'endpoint search comme dans le Flutter project.
        """
        log_info(f"Recherche du driver par query: {query}")
        if not query or not query.strip():
            log_error("Recherche driver avec query vide")
            return None
        
        # Utiliser search endpoint comme dans Flutter
        data = await self.http.search(EntityIds.DRIVER, query)
        
        if data and len(data) > 0:
            log_debug(f"Réponse API brute: {data[0]}")
            driver = self._map_to_driver(data[0])
            log_debug(f"Driver après mapping - ID: {driver.id}, serial: '{driver.serial_number}', name: '{driver.name}'")
            log_success(f"Driver trouvé: {driver.name if driver.name else '(nom vide)'} (serial: {driver.serial_number if driver.serial_number else '(vide)'}, ID: {driver.id})")
            return driver
        
        log_warning(f"Driver non trouvé: {query}")
        return None

    def _map_to_driver(self, data: dict) -> Driver:
        log_debug(f"Driver API data brute: {data}")
        
        # Les données réelles sont dans le champ 'data' de la réponse API
        driver_data = data.get("data", data)
        log_debug(f"Driver data extrait: {driver_data}")
        
        serial_number = driver_data.get("serial_number") or driver_data.get("serialNumber") or driver_data.get("serial") or ""
        log_debug(f"Driver serial number extrait: '{serial_number}'")
        
        return Driver(
            id=data.get("id") or driver_data.get("id"),
            serial_number=serial_number,
            name=driver_data.get("name", ""),
        )

    def _driver_to_dict(self, driver: Driver) -> dict:
        return {
            "serialNumber": driver.serial_number,
            "name": driver.name,
        }

    # ==================== VEHICLE ====================

    async def get_all_vehicle(self) -> List[Vehicle]:
        data = await self.http.get_entity_instances(EntityIds.VEHICLE)
        return [self._map_to_vehicle(item) for item in (data or [])]

    async def get_vehicle_by_id(self, id: str) -> Optional[Vehicle]:
        data = await self.http.get_entity_instance_by_id(id)
        return self._map_to_vehicle(data) if data else None

    async def add_vehicle(self, vehicle: Vehicle) -> Optional[str]:
        data = self._vehicle_to_dict(vehicle)
        return await self.http.create_entity_instance(EntityIds.VEHICLE, data)

    async def update_vehicle(self, id: str, vehicle: Vehicle) -> bool:
        data = self._vehicle_to_dict(vehicle)
        data["id"] = id
        return await self.http.update_entity_instance(id, data)

    async def delete_vehicle(self, id: str) -> bool:
        return await self.http.delete_entity_instance(id)

    async def search_vehicle(self, query: str) -> Optional[Vehicle]:
        data = await self.http.search(EntityIds.VEHICLE, query)
        if data:
            return self._map_to_vehicle(data[0])
        return None

    def _map_to_vehicle(self, data: dict) -> Vehicle:
        # Les données réelles sont dans le champ 'data' de la réponse API
        vehicle_data = data.get("data", data)
        return Vehicle(
            id=data.get("id"),
            license_plate=vehicle_data.get("license_plate", ""),
            brand=vehicle_data.get("brand", ""),
            weight_capacity=float(vehicle_data.get("weight_capacity", 0)),
            volume_capacity=float(vehicle_data.get("volume_capacity", 0)),
        )

    def _vehicle_to_dict(self, vehicle: Vehicle) -> dict:
        return {
            "license_plate": vehicle.license_plate,
            "brand": vehicle.brand,
            "weight_capacity": vehicle.weight_capacity,
            "volume_capacity": vehicle.volume_capacity,
        }

    # ==================== PACKAGE ====================

    async def get_all_package(self, status_filter: Optional[PackageStatus] = None) -> List[Package]:
        """
        Récupère tous les packages, avec filtrage optionnel par statut.
        
        Args:
            status_filter: Si spécifié, filtre les packages par statut
            
        Returns:
            Liste des packages (éventuellement filtrés)
        """
        log_info(f"Récupération des packages" + (f" (statut: {status_filter.value})" if status_filter else ""))
        data = await self.http.get_entity_instances(EntityIds.PACKAGE)
        packages = [self._map_to_package(item) for item in (data or [])]
        
        # Filtrer par statut si demandé
        if status_filter:
            packages = [p for p in packages if p.status == status_filter]
            log_info(f"{len(packages)} package(s) avec le statut '{status_filter.value}'")
        
        # Enrichir uniquement les packages filtrés
        enriched_packages = await self._enrich_packages_with_addresses(packages)
        log_success(f"{len(enriched_packages)} package(s) récupéré(s)")
        return enriched_packages

    async def get_package_by_id(self, id: str) -> Optional[Package]:
        log_info(f"Récupération du package par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            package = self._map_to_package(data)
            # Enrichir avec l'adresse
            enriched = await self._enrich_packages_with_addresses([package])
            result = enriched[0] if enriched else package
            log_success(f"Package trouvé: {id}")
            return result
        log_error(f"Package non trouvé: {id}")
        return None

    async def add_package(self, package_item: Package) -> Optional[str]:
        data = self._package_to_dict(package_item)
        return await self.http.create_entity_instance(EntityIds.PACKAGE, data)

    async def update_package(self, id: str, package_item: Package) -> bool:
        data = self._package_to_dict(package_item)
        data["id"] = id
        return await self.http.update_entity_instance(id, data)

    async def delete_package(self, id: str) -> bool:
        return await self.http.delete_entity_instance(id)

    async def search_package(self, query: str) -> Optional[Package]:
        data = await self.http.search(EntityIds.PACKAGE, query)
        if data:
            return self._map_to_package(data[0])
        return None

    def _map_to_package(self, data: dict) -> Package:
        # Les données réelles sont dans le champ 'data' de la réponse API
        package_data = data.get("data", data)
        
        log_debug(f"Package API data: {data}")
        log_debug(f"Package data extrait: {package_data}")
        
        status_str = package_data.get("status", "planned")
        try:
            status = PackageStatus(status_str)
        except ValueError:
            status = PackageStatus.PLANNED

        delivery_date = None
        if package_data.get("delivery_date"):
            delivery_date = datetime.fromisoformat(package_data["delivery_date"].replace("Z", "+00:00"))

        return Package(
            id=data.get("id"),
            client_name=package_data.get("client_name", ""),
            address=package_data.get("address", ""),
            address_label=package_data.get("address_label"),
            weight=float(package_data.get("weight", 0)),
            volume=float(package_data.get("volume", 0)),
            description=package_data.get("description", ""),
            delivery_date=delivery_date or datetime.now(),
            is_fragile=package_data.get("is_fragile", False),
            status=status,
        )

    def _package_to_dict(self, package_item: Package) -> dict:
        return {
            "client_name": package_item.client_name,
            "address": package_item.address,
            "address_label": package_item.address_label,
            "weight": package_item.weight,
            "volume": package_item.volume,
            "description": package_item.description,
            "delivery_date": package_item.delivery_date.isoformat() if package_item.delivery_date else None,
            "is_fragile": package_item.is_fragile,
            "status": package_item.status.value,
        }

    async def _enrich_packages_with_addresses(self, packages: List[Package]) -> List[Package]:
        """
        Enrichit les packages avec les labels d'adresse.
        Le champ 'address' d'un package est une référence à l'entité ADDRESS.
        """
        if not packages:
            return []
        
        # Récupérer toutes les adresses
        try:
            addresses_data = await self.http.get_entity_instances(EntityIds.ADDRESS)
            if not addresses_data:
                return packages
            
            # Créer un mapping id -> label
            labels_by_id = {}
            for addr in addresses_data:
                addr_data = addr.get("data", addr)
                addr_id = addr.get("id")
                label = addr_data.get("label", "")
                if addr_id and label:
                    labels_by_id[addr_id] = label
            
            # Enrichir les packages
            enriched_packages = []
            for package in packages:
                if package.address in labels_by_id:
                    # Créer une copie du package avec le label d'adresse
                    enriched_package = Package(
                        id=package.id,
                        client_name=package.client_name,
                        address=package.address,
                        address_label=labels_by_id[package.address],
                        weight=package.weight,
                        volume=package.volume,
                        description=package.description,
                        delivery_date=package.delivery_date,
                        is_fragile=package.is_fragile,
                        status=package.status,
                    )
                    enriched_packages.append(enriched_package)
                else:
                    enriched_packages.append(package)
            
            return enriched_packages
            
        except Exception as e:
            log_error(f"Erreur lors de l'enrichissement des adresses: {e}")
            return packages

    # ==================== ADDRESS ====================

    async def get_all_address(self) -> List[Address]:
        log_info("Récupération de toutes les adresses")
        data = await self.http.get_entity_instances(EntityIds.ADDRESS)
        result = [self._map_to_address(item) for item in (data or [])]
        log_success(f"{len(result)} adresse(s) récupérée(s)")
        return result

    async def get_address_by_id(self, id: str) -> Optional[Address]:
        """Récupère une adresse par son ID."""
        log_info(f"Récupération de l'adresse par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Adresse trouvée: {id}")
            return self._map_to_address(data)
        log_error(f"Adresse non trouvée: {id}")
        return None

    async def add_address(self, address: Address) -> Optional[str]:
        data = self._address_to_dict(address)
        return await self.http.create_entity_instance(EntityIds.ADDRESS, data)

    async def update_address(self, id: str, address: Address) -> bool:
        data = self._address_to_dict(address)
        data["id"] = id
        return await self.http.update_entity_instance(id, data)

    async def delete_address(self, id: str) -> bool:
        return await self.http.delete_entity_instance(id)

    def _map_to_address(self, data: dict) -> Address:
        # Les données réelles sont dans le champ 'data' de la réponse API
        address_data = data.get("data", data)
        return Address(
            id=data.get("id"),
            label=address_data.get("label", ""),
            latitude=float(address_data.get("latitude", 0)),
            longitude=float(address_data.get("longitude", 0)),
        )

    def _address_to_dict(self, address: Address) -> dict:
        return {
            "label": address.label,
            "latitude": address.latitude,
            "longitude": address.longitude,
        }

    # ==================== SCHEDULE ====================

    async def get_all_schedule(self) -> List[Schedule]:
        log_info("Récupération de tous les schedules")
        data = await self.http.get_entity_instances(EntityIds.SCHEDULE)
        result = [self._map_to_schedule(item) for item in (data or [])]
        log_success(f"{len(result)} schedule(s) récupéré(s)")
        return result

    async def get_schedule_by_id(self, id: str) -> Optional[Schedule]:
        log_info(f"Récupération du schedule par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Schedule trouvé: {id}")
            return self._map_to_schedule(data)
        log_error(f"Schedule non trouvé: {id}")
        return None

    async def add_schedule(self, schedule: Schedule) -> Optional[str]:
        log_info(f"Création d'un nouveau schedule")
        data = self._schedule_to_dict(schedule)
        result = await self.http.create_entity_instance(EntityIds.SCHEDULE, data)
        if result:
            log_success(f"Schedule créé avec ID: {result}")
        else:
            log_error("Échec de la création du schedule")
        return result

    async def update_schedule(self, id: str, schedule: Schedule) -> bool:
        log_info(f"Mise à jour du schedule: {id}")
        data = self._schedule_to_dict(schedule)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Schedule {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du schedule: {id}")
        return result

    async def delete_schedule(self, id: str) -> bool:
        log_info(f"Suppression du schedule: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Schedule {id} supprimé")
        else:
            log_error(f"Échec de la suppression du schedule: {id}")
        return result

    async def search_schedule(self, query: str) -> Optional[Schedule]:
        log_info(f"Recherche du schedule par query: {query}")
        data = await self.http.search(EntityIds.SCHEDULE, query)
        if data:
            log_success(f"Schedule trouvé: {query}")
            return self._map_to_schedule(data[0])
        log_warning(f"Schedule non trouvé: {query}")
        return None

    async def get_schedule_by_driver_serial_number(self, driver_serial_number: str) -> List[Schedule]:
        """
        Récupère les schedules par driver.
        Utilise l'endpoint /entity-instances/by-reference/{driverId} et filtre les schedules.
        """
        log_info(f"Recherche des schedules par driver serial number: {driver_serial_number}")
        
        # D'abord, trouver le driver par son serial number pour obtenir son ID
        driver = await self.search_driver(driver_serial_number)
        if not driver:
            log_error(f"Driver non trouvé: {driver_serial_number}")
            return []
        
        # Utiliser l'endpoint by-reference qui retourne TOUTES les entités liées au driver
        log_info(f"Recherche des entités par référence pour le driver ID: {driver.id}")
        all_entities = await self.http.get_entity_instance_by_references(
            EntityIds.SCHEDULE, "driver_serial_number", driver.id
        )
        
        if not all_entities:
            log_warning(f"Aucune entité trouvée pour le driver {driver.id}")
            return []
        
        # Filtrer pour ne garder que les schedules (entityId = Schedule entity ID)
        schedules_data = [
            e for e in all_entities 
            if e.get("entityId") == EntityIds.SCHEDULE
        ]
        
        log_info(f"{len(schedules_data)} schedule(s) trouvé(s) sur {len(all_entities)} entité(s)")
        
        result = [self._map_to_schedule(item) for item in schedules_data]
        log_success(f"{len(result)} schedule(s) pour le driver {driver.id}")
        return result

    async def get_schedule_by_vehicle_license_plate(self, vehicle_license_plate: str) -> List[Schedule]:
        """
        Récupère les schedules par véhicule.
        Note: vehicle_license_plate dans l'API est une référence à vehicle.id
        """
        log_info(f"Recherche des schedules par vehicle license plate: {vehicle_license_plate}")

        # D'abord, trouver le véhicule par sa plaque pour obtenir son ID
        vehicle = await self.search_vehicle(vehicle_license_plate)
        if not vehicle:
            log_error(f"Véhicule non trouvé: {vehicle_license_plate}")
            return []

        # Utiliser l'ID du véhicule pour chercher les schedules
        log_info(f"Recherche des schedules pour le vehicle ID: {vehicle.id}")
        data = await self.http.get_entity_instance_by_references(
            EntityIds.SCHEDULE, "vehicle_license_plate", vehicle.id
        )
        result = [self._map_to_schedule(item) for item in (data or [])]
        log_success(f"{len(result)} schedule(s) trouvé(s) pour le véhicule {vehicle.id}")
        return result

    def _map_to_schedule(self, data: dict) -> Schedule:
        # Les données réelles sont dans le champ 'data' de la réponse API
        schedule_data = data.get("data", data)
        
        log_debug(f"Schedule API data: {data}")
        log_debug(f"Schedule data extrait: {schedule_data}")
        
        delivery_date = None
        if schedule_data.get("delivery_date"):
            delivery_date = datetime.fromisoformat(schedule_data["delivery_date"].replace("Z", "+00:00"))

        return Schedule(
            id=data.get("id"),
            delivery_date=delivery_date or datetime.now(),
            driver_serial_number=schedule_data.get("driver_serial_number", ""),
            vehicle_license_plate=schedule_data.get("vehicle_license_plate", ""),
        )

    def _schedule_to_dict(self, schedule: Schedule) -> dict:
        return {
            "delivery_date": schedule.delivery_date.isoformat() if schedule.delivery_date else None,
            "driver_serial_number": schedule.driver_serial_number,
            "vehicle_license_plate": schedule.vehicle_license_plate,
        }

    # ==================== DRIVER AVAILABILITY ====================

    async def get_all_driver_availability(self) -> List[DriverAvailability]:
        log_info("Récupération de tous les driver availability")
        data = await self.http.get_entity_instances(EntityIds.DRIVER_AVAILABILITY)
        result = [self._map_to_driver_availability(item) for item in (data or [])]
        log_success(f"{len(result)} driver availability(s) récupéré(s)")
        return result

    async def get_driver_availability_by_id(self, id: str) -> Optional[DriverAvailability]:
        log_info(f"Récupération du driver availability par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Driver availability trouvé: {id}")
            return self._map_to_driver_availability(data)
        log_error(f"Driver availability non trouvé: {id}")
        return None

    async def add_driver_availability(self, availability: DriverAvailability) -> Optional[str]:
        log_info(f"Création d'un nouveau driver availability")
        data = self._driver_availability_to_dict(availability)
        result = await self.http.create_entity_instance(EntityIds.DRIVER_AVAILABILITY, data)
        if result:
            log_success(f"Driver availability créé avec ID: {result}")
        else:
            log_error("Échec de la création du driver availability")
        return result

    async def update_driver_availability(self, id: str, availability: DriverAvailability) -> bool:
        log_info(f"Mise à jour du driver availability: {id}")
        data = self._driver_availability_to_dict(availability)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Driver availability {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du driver availability: {id}")
        return result

    async def delete_driver_availability(self, id: str) -> bool:
        log_info(f"Suppression du driver availability: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Driver availability {id} supprimé")
        else:
            log_error(f"Échec de la suppression du driver availability: {id}")
        return result

    async def search_driver_availability(self, query: str) -> Optional[DriverAvailability]:
        log_info(f"Recherche du driver availability par query: {query}")
        data = await self.http.search(EntityIds.DRIVER_AVAILABILITY, query)
        if data:
            log_success(f"Driver availability trouvé: {query}")
            return self._map_to_driver_availability(data[0])
        log_warning(f"Driver availability non trouvé: {query}")
        return None

    async def get_driver_availability_by_driver_id(self, driver_id: str) -> List[DriverAvailability]:
        """
        Récupère les disponibilités par driver.
        Note: driver_id est une référence à driver.id
        """
        log_info(f"Recherche des disponibilités par driver ID: {driver_id}")
        data = await self.http.get_entity_instance_by_references(
            EntityIds.DRIVER_AVAILABILITY, "driver_id", driver_id
        )
        result = [self._map_to_driver_availability(item) for item in (data or [])]
        log_success(f"{len(result)} disponibilité(s) trouvée(s) pour le driver {driver_id}")
        return result

    def _map_to_driver_availability(self, data: dict) -> DriverAvailability:
        # Les données réelles sont dans le champ 'data' de la réponse API
        da_data = data.get("data", data)
        available_date = None
        if da_data.get("available_date"):
            available_date = datetime.fromisoformat(da_data["available_date"].replace("Z", "+00:00"))

        return DriverAvailability(
            id=data.get("id"),
            driver_id=da_data.get("driver_id", ""),
            available_date=available_date or datetime.now(),
        )

    def _driver_availability_to_dict(self, availability: DriverAvailability) -> dict:
        return {
            "driver_id": availability.driver_id,
            "available_date": availability.available_date.isoformat() if availability.available_date else None,
        }

    # ==================== SCHEDULE PACKAGE ====================

    async def get_all_schedule_package(self) -> List[SchedulePackage]:
        log_info("Récupération de tous les schedule package")
        data = await self.http.get_entity_instances(EntityIds.SCHEDULE_PACKAGE)
        result = [self._map_to_schedule_package(item) for item in (data or [])]
        log_success(f"{len(result)} schedule package(s) récupéré(s)")
        return result

    async def get_schedule_package_by_id(self, id: str) -> Optional[SchedulePackage]:
        log_info(f"Récupération du schedule package par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Schedule package trouvé: {id}")
            return self._map_to_schedule_package(data)
        log_error(f"Schedule package non trouvé: {id}")
        return None

    async def add_schedule_package(self, schedule_package: SchedulePackage) -> Optional[str]:
        log_info(f"Création d'un nouveau schedule package")
        data = self._schedule_package_to_dict(schedule_package)
        result = await self.http.create_entity_instance(EntityIds.SCHEDULE_PACKAGE, data)
        if result:
            log_success(f"Schedule package créé avec ID: {result}")
        else:
            log_error("Échec de la création du schedule package")
        return result

    async def update_schedule_package(self, id: str, schedule_package: SchedulePackage) -> bool:
        log_info(f"Mise à jour du schedule package: {id}")
        data = self._schedule_package_to_dict(schedule_package)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Schedule package {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du schedule package: {id}")
        return result

    async def delete_schedule_package(self, id: str) -> bool:
        log_info(f"Suppression du schedule package: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Schedule package {id} supprimé")
        else:
            log_error(f"Échec de la suppression du schedule package: {id}")
        return result

    async def search_schedule_package(self, query: str) -> Optional[SchedulePackage]:
        log_info(f"Recherche du schedule package par query: {query}")
        data = await self.http.search(EntityIds.SCHEDULE_PACKAGE, query)
        if data:
            log_success(f"Schedule package trouvé: {query}")
            return self._map_to_schedule_package(data[0])
        log_warning(f"Schedule package non trouvé: {query}")
        return None

    async def get_schedule_package_by_schedule_id(self, schedule_id: str) -> List[SchedulePackage]:
        """
        Récupère les packages d'un schedule.
        Utilise l'endpoint /entity-instances/by-reference/{scheduleId} et filtre.
        """
        log_info(f"Recherche des packages pour le schedule: {schedule_id}")
        
        # Utiliser l'endpoint by-reference
        all_entities = await self.http.get_entity_instance_by_references(
            EntityIds.SCHEDULE_PACKAGE, "schedule_id", schedule_id
        )
        
        if not all_entities:
            log_warning(f"Aucune entité trouvée pour le schedule {schedule_id}")
            return []
        
        # Filtrer pour ne garder que les schedule_packages
        sp_data = [
            e for e in all_entities 
            if e.get("entityId") == EntityIds.SCHEDULE_PACKAGE
        ]
        
        log_debug(f"SchedulePackage API data: {sp_data}")
        
        result = [self._map_to_schedule_package(item) for item in sp_data]
        log_success(f"{len(result)} package(s) trouvé(s) pour le schedule {schedule_id}")
        return result

    async def get_schedule_package_by_package_id(self, package_id: str) -> List[SchedulePackage]:
        """
        Récupère les schedules d'un package.
        Note: package_id est une référence à package.id
        """
        log_info(f"Recherche des schedules pour le package: {package_id}")
        data = await self.http.get_entity_instance_by_references(
            EntityIds.SCHEDULE_PACKAGE, "package_id", package_id
        )
        result = [self._map_to_schedule_package(item) for item in (data or [])]
        log_success(f"{len(result)} schedule(s) trouvé(s) pour le package {package_id}")
        return result

    def _map_to_schedule_package(self, data: dict) -> SchedulePackage:
        # Les données réelles sont dans le champ 'data' de la réponse API
        sp_data = data.get("data", data)
        return SchedulePackage(
            id=data.get("id"),
            schedule_id=sp_data.get("schedule_id", ""),
            package_id=sp_data.get("package_id", ""),
            position=sp_data.get("position"),
        )

    def _schedule_package_to_dict(self, schedule_package: SchedulePackage) -> dict:
        return {
            "scheduleId": schedule_package.schedule_id,
            "packageId": schedule_package.package_id,
            "position": schedule_package.position,
        }

    # ==================== DELIVERY FAILURE ====================

    async def get_all_delivery_failure(self) -> List[DeliveryFailure]:
        log_info("Récupération de tous les delivery failure")
        data = await self.http.get_entity_instances(EntityIds.DELIVERY_FAILURE)
        result = [self._map_to_delivery_failure(item) for item in (data or [])]
        log_success(f"{len(result)} delivery failure(s) récupéré(s)")
        return result

    async def get_delivery_failure_by_id(self, id: str) -> Optional[DeliveryFailure]:
        log_info(f"Récupération du delivery failure par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Delivery failure trouvé: {id}")
            return self._map_to_delivery_failure(data)
        log_error(f"Delivery failure non trouvé: {id}")
        return None

    async def add_delivery_failure(self, delivery_failure: DeliveryFailure) -> Optional[str]:
        log_info(f"Création d'un nouveau delivery failure")
        data = self._delivery_failure_to_dict(delivery_failure)
        result = await self.http.create_entity_instance(EntityIds.DELIVERY_FAILURE, data)
        if result:
            log_success(f"Delivery failure créé avec ID: {result}")
        else:
            log_error("Échec de la création du delivery failure")
        return result

    async def update_delivery_failure(self, id: str, delivery_failure: DeliveryFailure) -> bool:
        log_info(f"Mise à jour du delivery failure: {id}")
        data = self._delivery_failure_to_dict(delivery_failure)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Delivery failure {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du delivery failure: {id}")
        return result

    async def delete_delivery_failure(self, id: str) -> bool:
        log_info(f"Suppression du delivery failure: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Delivery failure {id} supprimé")
        else:
            log_error(f"Échec de la suppression du delivery failure: {id}")
        return result

    async def search_delivery_failure(self, query: str) -> Optional[DeliveryFailure]:
        log_info(f"Recherche du delivery failure par query: {query}")
        data = await self.http.search(EntityIds.DELIVERY_FAILURE, query)
        if data:
            log_success(f"Delivery failure trouvé: {query}")
            return self._map_to_delivery_failure(data[0])
        log_warning(f"Delivery failure non trouvé: {query}")
        return None

    async def get_delivery_failure_by_package_id(self, package_id: str) -> List[DeliveryFailure]:
        """
        Récupère les failures par package.
        Note: package_id est une référence à package.id
        """
        log_info(f"Recherche des failures pour le package: {package_id}")
        data = await self.http.get_entity_instance_by_references(
            EntityIds.DELIVERY_FAILURE, "package_id", package_id
        )
        result = [self._map_to_delivery_failure(item) for item in (data or [])]
        log_success(f"{len(result)} failure(s) trouvé(s) pour le package {package_id}")
        return result

    def _map_to_delivery_failure(self, data: dict) -> DeliveryFailure:
        # Les données réelles sont dans le champ 'data' de la réponse API
        df_data = data.get("data", data)
        return DeliveryFailure(
            id=data.get("id"),
            package_id=df_data.get("package_id", ""),
            cause=int(df_data.get("cause", 0)),
            comment=df_data.get("comment", ""),
        )

    def _delivery_failure_to_dict(self, delivery_failure: DeliveryFailure) -> dict:
        return {
            "package_id": delivery_failure.package_id,
            "cause": delivery_failure.cause,
            "comment": delivery_failure.comment,
        }

    # ==================== UNATTENDED DROP OFF ====================

    async def get_all_unattended_drop_off(self) -> List[UnattendedDropOff]:
        log_info("Récupération de tous les unattended drop off")
        data = await self.http.get_entity_instances(EntityIds.UNATTENDED_DROP_OFF)
        result = [self._map_to_unattended_drop_off(item) for item in (data or [])]
        log_success(f"{len(result)} unattended drop off(s) récupéré(s)")
        return result

    async def get_unattended_drop_off_by_id(self, id: str) -> Optional[UnattendedDropOff]:
        log_info(f"Récupération du unattended drop off par ID: {id}")
        data = await self.http.get_entity_instance_by_id(id)
        if data:
            log_success(f"Unattended drop off trouvé: {id}")
            return self._map_to_unattended_drop_off(data)
        log_error(f"Unattended drop off non trouvé: {id}")
        return None

    async def add_unattended_drop_off(self, drop_off: UnattendedDropOff) -> Optional[str]:
        log_info(f"Création d'un nouveau unattended drop off")
        data = self._unattended_drop_off_to_dict(drop_off)
        result = await self.http.create_entity_instance(EntityIds.UNATTENDED_DROP_OFF, data)
        if result:
            log_success(f"Unattended drop off créé avec ID: {result}")
        else:
            log_error("Échec de la création du unattended drop off")
        return result

    async def update_unattended_drop_off(self, id: str, drop_off: UnattendedDropOff) -> bool:
        log_info(f"Mise à jour du unattended drop off: {id}")
        data = self._unattended_drop_off_to_dict(drop_off)
        data["id"] = id
        result = await self.http.update_entity_instance(id, data)
        if result:
            log_success(f"Unattended drop off {id} mis à jour")
        else:
            log_error(f"Échec de la mise à jour du unattended drop off: {id}")
        return result

    async def delete_unattended_drop_off(self, id: str) -> bool:
        log_info(f"Suppression du unattended drop off: {id}")
        result = await self.http.delete_entity_instance(id)
        if result:
            log_success(f"Unattended drop off {id} supprimé")
        else:
            log_error(f"Échec de la suppression du unattended drop off: {id}")
        return result

    async def search_unattended_drop_off(self, query: str) -> Optional[UnattendedDropOff]:
        log_info(f"Recherche du unattended drop off par query: {query}")
        data = await self.http.search(EntityIds.UNATTENDED_DROP_OFF, query)
        if data:
            log_success(f"Unattended drop off trouvé: {query}")
            return self._map_to_unattended_drop_off(data[0])
        log_warning(f"Unattended drop off non trouvé: {query}")
        return None

    async def get_unattended_drop_off_by_package_id(self, package_id: str) -> List[UnattendedDropOff]:
        """
        Récupère les drop off par package.
        Note: package_id est une référence à package.id
        """
        log_info(f"Recherche des drop off pour le package: {package_id}")
        data = await self.http.get_entity_instance_by_references(
            EntityIds.UNATTENDED_DROP_OFF, "package_id", package_id
        )
        result = [self._map_to_unattended_drop_off(item) for item in (data or [])]
        log_success(f"{len(result)} drop off(s) trouvé(s) pour le package {package_id}")
        return result

    def _map_to_unattended_drop_off(self, data: dict) -> UnattendedDropOff:
        # Les données réelles sont dans le champ 'data' de la réponse API
        udo_data = data.get("data", data)
        return UnattendedDropOff(
            id=data.get("id"),
            package_id=udo_data.get("package_id", ""),
            drop_off_location=udo_data.get("drop_off_location", ""),
            photo_path=udo_data.get("photo_path", ""),
        )

    def _unattended_drop_off_to_dict(self, drop_off: UnattendedDropOff) -> dict:
        return {
            "package_id": drop_off.package_id,
            "drop_off_location": drop_off.drop_off_location,
            "photo_path": drop_off.photo_path,
        }
