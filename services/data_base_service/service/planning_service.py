"""
Planning Service - Service de gestion des livraisons et packages

Ce module fournit les fonctions essentielles pour :
- Récupérer les livraisons d'un driver sous forme de Trips ordonnés
- Exporter automatiquement les trips dans un fichier JSON
- Mettre à jour le statut d'un package
- Ajouter un échec de livraison (delivery failure)

Note: Seuls les packages avec le statut 'planned' sont inclus dans les trips.
"""


class DriverNotFoundError(Exception):
    """Levée quand un driver_serial_number n'existe pas en base de données."""
    pass

import asyncio
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from .http_request_services import HttpRequestServices
from .crud_service import CrudService
from .token_manager import TokenManager
from .logger_service import log_info, log_error, log_success, log_warning
from ..entities.models import Driver, Schedule, Package, SchedulePackage, Trip, Address, DeliveryFailure
from ..entities.enum.package_status import PackageStatus


def get_today_date() -> str:
    """Retourne la date du jour au format YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


class PlanningService:
    """
    Service de gestion des livraisons et packages.
    
    Méthodes publiques :
    - get_delivery_trips() : Récupère les trips ordonnés + export JSON auto
    - update_package_status() : Met à jour le statut d'un package
    - add_delivery_failure() : Ajoute un échec de livraison
    """
    
    def __init__(self, token_manager: Optional[TokenManager] = None):
        """Initialise le service."""
        self.token_manager = token_manager or TokenManager()
        self._http: Optional[HttpRequestServices] = None
        self._crud: Optional[CrudService] = None
    
    async def _init_services(self):
        """Initialise les services HTTP et CRUD"""
        if self._http is None:
            self._http = HttpRequestServices()
            self._crud = CrudService(self._http)
            token = await self.token_manager.get_valid_token(self._http)
            if not token:
                raise Exception("Impossible d'obtenir un token valide")
            self._http.set_token(token)
    
    async def close(self):
        """Ferme la session HTTP"""
        if self._http:
            await self._http.close()
            self._http = None
            self._crud = None
    
    async def get_delivery_trips(
        self,
        driver_serial_number: str,
        date: Optional[str] = None,
    ) -> bool:
        await self._init_services()
        log_info(f"Récupération des trips pour le driver: {driver_serial_number}")
        
        # 1. Chercher le driver
        driver = await self._crud.search_driver(driver_serial_number)
        if not driver:
            log_error(f"Driver non trouvé: {driver_serial_number}")
            raise DriverNotFoundError(f"Driver not found: {driver_serial_number}")
        
        log_success(f"Driver trouvé: {driver.name} (ID: {driver.id})")
        
        # 2. Récupérer les schedules du driver
        schedules = await self._crud.get_schedule_by_driver_serial_number(driver.serial_number)
        if not schedules:
            log_warning(f"Aucun schedule trouvé pour le driver: {driver_serial_number}")
            return False
        
        # 3. Filtrer par date
        target_date = date or get_today_date()
        today_schedules = [
            s for s in schedules
            if s.delivery_date.strftime("%Y-%m-%d") == target_date
        ]
        
        if not today_schedules:
            log_warning(f"Aucun schedule pour la date: {target_date}")
            return False
        
        # 4. Récupérer les schedule_packages et trier par position
        all_schedule_packages = []
        for schedule in today_schedules:
            schedule_packages = await self._crud.get_schedule_package_by_schedule_id(schedule.id)
            all_schedule_packages.extend(schedule_packages)
        
        all_schedule_packages.sort(key=lambda sp: sp.position if sp.position is not None else float('inf'))
        
        # 5. Créer les trips (uniquement 'planned')
        trips = []
        for sp in all_schedule_packages:
            package = await self._crud.get_package_by_id(sp.package_id)
            if not package or package.status != PackageStatus.PLANNED:
                continue
            
            address = None
            if package.address:
                try:
                    address = await self._crud.get_address_by_id(package.address)
                except Exception as e:
                    log_warning(f"Erreur adresse {package.address}: {e}")
            
            trips.append(Trip.from_package(package, address))
        
        log_success(f"{len(trips)} trip(s) créé(s)")
        
        # 6. Charger dans UtilityService
        try:
            from services.utility_service import UtilityService
            trips_data = [trip.to_dict() for trip in trips]
            for t in trips_data:
                if "name" in t:
                    t["address"] = t.pop("name")
            UtilityService().load_from_trips(trips_data)
            log_success(f"{len(trips)} trip(s) chargés en mémoire")
            return True
        except Exception as e:
            log_warning(f"Impossible de charger dans UtilityService: {e}")
            return False
    
    async def update_package_status(
        self,
        package_id: str,
        new_status: PackageStatus
    ) -> bool:
        """
        Met à jour le statut d'un package.

        Args:
            package_id: ID du package
            new_status: Nouveau statut

        Returns:
            True si la mise à jour a réussi
        """
        await self._init_services()
        log_info(f"Mise à jour du package {package_id} vers: {new_status.value}")

        package = await self._crud.get_package_by_id(package_id)
        if not package:
            log_error(f"Package non trouvé: {package_id}")
            return False

        old_status = package.status
        package.status = new_status
        success = await self._crud.update_package(package_id, package)

        if success:
            log_success(f"Package {package_id} mis à jour: {old_status.value} -> {new_status.value}")
            await self._remove_package_from_data_json(package_id)

        else:
            log_error(f"Échec de la mise à jour du package: {package_id}")

        return success
    
    async def _remove_package_from_data_json(self, package_id: str) -> None:
        try:
            from services.utility_service import UtilityService
            u = UtilityService()
            #u.remove_trip(str(package_id))#
            log_success(f"Package {package_id} retiré du cache")
        except Exception as e:
            log_warning(f"Impossible de mettre à jour UtilityService: {e}")

    async def add_delivery_failure(
        self,
        package_id: str,
        cause: int,
        comment: str
    ) -> bool:
        """
        Ajoute un échec de livraison pour un package.
        
        Args:
            package_id: ID du package concerné
            cause: Cause de l'échec (1 à 6)
            comment: Commentaire décrivant l'échec
            
        Returns:
            True si l'ajout a réussi
        """
        await self._init_services()
        
        if not 1 <= cause <= 6:
            raise ValueError("La cause doit être un nombre entre 1 et 6")
        
        log_info(f"Ajout échec livraison pour {package_id} (cause: {cause})")
        
        package = await self._crud.get_package_by_id(package_id)
        if not package:
            log_error(f"Package non trouvé: {package_id}")
            return False
        
        delivery_failure = DeliveryFailure(package_id=package_id, cause=cause, comment=comment)
        failure_id = await self._crud.add_delivery_failure(delivery_failure)
        
        if failure_id:
            log_success(f"Échec de livraison ajouté pour le package {package_id}")
            package.status = PackageStatus.DELIVERY_FAILURE
            await self._crud.update_package(package_id, package)
            return True
        else:
            log_error(f"Échec de l'ajout de l'échec de livraison pour le package {package_id}")
            return False


# Fonctions utilitaires

async def get_delivery_trips(
    driver_serial_number: str,
    date: Optional[str] = None,
    export_json: bool = True,
    output_file: Optional[str] = None
) -> List[Trip]:
    """Récupère les trips ordonnés d'un driver avec export JSON automatique."""
    service = PlanningService()
    try:
        return await service.get_delivery_trips(
            driver_serial_number,
            date=date,
            export_json=export_json,
            output_file=output_file
        )
    finally:
        await service.close()


async def update_package(package_id: str, new_status: PackageStatus) -> bool:
    """Met à jour le statut d'un package."""
    service = PlanningService()
    try:
        return await service.update_package_status(package_id, new_status)
    finally:
        await service.close()


async def add_delivery_failure(package_id: str, cause: int, comment: str) -> bool:
    """Ajoute un échec de livraison pour un package."""
    service = PlanningService()
    try:
        return await service.add_delivery_failure(package_id, cause, comment)
    finally:
        await service.close()
