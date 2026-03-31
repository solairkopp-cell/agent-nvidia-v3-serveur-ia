#!/usr/bin/env python3
"""
CLI - Récupérer les livraisons assignées à un driver pour la date actuelle
et mettre à jour le statut des packages
"""

import asyncio
from datetime import datetime
from typing import Optional
from pathlib import Path

from service import (
    HttpRequestServices, 
    CrudService, 
    TokenManager,
    log_info,
    log_error,
    log_success,
    log_warning,
    log_debug,
)
from entities.models import Driver, Schedule, Package, SchedulePackage
from entities.enum.package_status import PackageStatus


def get_today_date() -> str:
    """Retourne la date du jour au format YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


async def get_driver_deliveries(
    driver_serial_number: str, 
    debug: bool = False,
    token_manager: Optional[TokenManager] = None
) -> Optional[list[dict]]:
    """
    Récupère toutes les livraisons assignées à un driver pour la date actuelle.
    
    Args:
        driver_serial_number: Le numéro de série du driver
        debug: Si True, affiche les informations de débogage
        token_manager: Gestionnaire de token (optionnel, créé si non fourni)
        
    Returns:
        Liste des livraisons avec les détails des packages
    """
    http = HttpRequestServices()
    crud = CrudService(http)
    
    # Utiliser le token manager fourni ou en créer un nouveau
    if token_manager is None:
        token_manager = TokenManager()
    
    try:
        # 0. Obtenir un token valide (cache ou nouveau login)
        log_info(f"Démarrage de la récupération des livraisons pour le driver: {driver_serial_number}")
        print("🔐 Vérification du token...")
        token = await token_manager.get_valid_token(http)
        
        if not token:
            log_error("Impossible d'obtenir un token valide")
            print("❌ Impossible d'obtenir un token valide")
            return None
        
        http.set_token(token)
        
        # 1. Chercher le driver par son numéro de série
        print(f"🔍 Recherche du driver avec le numéro de série: {driver_serial_number}")
        driver = await crud.search_driver(driver_serial_number)
        
        if not driver:
            log_error(f"Aucun driver trouvé avec le numéro de série: {driver_serial_number}")
            print(f"❌ Aucun driver trouvé avec le numéro de série: {driver_serial_number}")
            return None
        
        log_success(f"Driver trouvé: {driver.name} (ID: {driver.id})")
        print(f"✅ Driver trouvé: {driver.name} (ID: {driver.id})")
        
        # 2. Récupérer TOUS les schedules du driver
        print(f"📅 Recherche de tous les schedules du driver...")
        schedules = await crud.get_schedule_by_driver_serial_number(driver.serial_number)
        
        if not schedules:
            log_warning(f"Aucune livraison trouvée pour le driver: {driver_serial_number}")
            print("⚠️  Aucune livraison trouvée pour ce driver")
            return []
        
        log_info(f"{len(schedules)} schedule(s) trouvé(s) pour le driver: {driver_serial_number}")
        print(f"📋 {len(schedules)} schedule(s) trouvé(s) au total")
        
        if debug:
            print("\n--- DEBUG: Tous les schedules ---")
            for s in schedules:
                print(f"  ID: {s.id}, Date: {s.delivery_date}, Formatted: {s.delivery_date.strftime('%Y-%m-%d')}")
            print("--- FIN DEBUG ---\n")
        
        # 3. Filtrer les schedules pour la date actuelle
        today = get_today_date()
        today_schedules = [
            s for s in schedules 
            if s.delivery_date.strftime("%Y-%m-%d") == today
        ]
        
        if debug:
            print(f"\n--- DEBUG: Date recherchée: {today} ---")
            for s in schedules:
                match = "✓" if s.delivery_date.strftime("%Y-%m-%d") == today else "✗"
                print(f"  {match} {s.delivery_date.strftime('%Y-%m-%d')} == {today}")
            print("--- FIN DEBUG ---\n")
        
        if not today_schedules:
            log_warning(f"Aucune livraison prévue pour aujourd'hui ({today})")
            print(f"⚠️  Aucune livraison prévue pour aujourd'hui ({today})")
            if debug and schedules:
                print(f"\nDates disponibles:")
                for s in schedules:
                    print(f"  - {s.delivery_date.strftime('%Y-%m-%d')}")
            return []
        
        log_success(f"{len(today_schedules)} tournée(s) trouvée(s) pour aujourd'hui")
        print(f"📦 {len(today_schedules)} tournée(s) trouvée(s) pour aujourd'hui")
        
        # 4. Récupérer les packages pour chaque schedule
        # Filtrer uniquement les packages avec le statut 'planned'
        deliveries = []
        for schedule in today_schedules:
            log_info(f"Récupération des packages pour le schedule: {schedule.id}")
            schedule_packages = await crud.get_schedule_package_by_schedule_id(schedule.id)

            packages_info = []
            for sp in schedule_packages:
                package = await crud.get_package_by_id(sp.package_id)
                if package:
                    # Filtrer: ne garder que les packages avec statut 'planned'
                    if package.status.value == "planned":
                        packages_info.append({
                            "package_id": package.id,
                            "client_name": package.client_name,
                            "address": package.address,
                            "address_label": package.address_label,
                            "weight": package.weight,
                            "volume": package.volume,
                            "description": package.description,
                            "is_fragile": package.is_fragile,
                            "status": package.status.value,
                            "position": sp.position,
                        })

            # Trier les packages par position
            packages_info.sort(key=lambda x: x["position"] if x["position"] is not None else 999)

            deliveries.append({
                "schedule_id": schedule.id,
                "vehicle_license_plate": schedule.vehicle_license_plate,
                "delivery_date": schedule.delivery_date.isoformat(),
                "packages": packages_info,
                "total_packages": len(packages_info),
            })

        # Filtrer les schedules sans packages 'planned'
        deliveries = [d for d in deliveries if d["total_packages"] > 0]

        total_packages = sum(d["total_packages"] for d in deliveries)
        log_success(f"Récupération terminée: {len(deliveries)} tournée(s), {total_packages} colis 'planned'")

        return deliveries
        
    except Exception as e:
        log_error(f"Exception lors de la récupération des livraisons: {e}")
        print(f"❌ Erreur: {e}")
        return None
    finally:
        await http.close()


async def update_package_status_cli(
    packages: list[dict],
    token_manager: TokenManager
):
    """
    Permet de mettre à jour le statut d'un package depuis la liste affichée.
    """
    print()
    print("=" * 60)
    print("🔄 METTRE À JOUR LE STATUT D'UN PACKAGE")
    print("=" * 60)
    print()
    
    # Filtrer uniquement les packages 'planned' pour la mise à jour
    planned_packages = [p for p in packages if p["status"] == "planned"]
    
    if not planned_packages:
        print("ℹ️  Aucun package avec le statut 'planned' dans cette liste")
        print("   Seuls les packages 'planned' peuvent être mis à jour.")
        return
    
    # Afficher les packages planned avec index
    for i, pkg in enumerate(planned_packages, 1):
        status_icon = "📋"  # Tous sont 'planned'
        fragile_mark = " 🧊" if pkg["is_fragile"] else ""
        address_label = f" ({pkg['address_label']})" if pkg["address_label"] else ""
        
        print(f"  [{i:2d}] {status_icon} {pkg['client_name']}{fragile_mark}")
        print(f"       📍 {pkg['address']}{address_label}")
        print(f"       📊 Statut: {pkg['status']}")
        print()
    
    # Demander de choisir un package
    while True:
        try:
            choice = input(f"Choisissez un package (1-{len(planned_packages)}) ou 0 pour annuler: ").strip()
            package_index = int(choice)
            
            if package_index == 0:
                print("❌ Annulé")
                return
            
            if 1 <= package_index <= len(planned_packages):
                break
            
            print(f"❌ Veuillez entrer un nombre entre 1 et {len(planned_packages)}")
        except ValueError:
            print("❌ Entrée invalide, veuillez entrer un nombre")
    
    selected_pkg = planned_packages[package_index - 1]
    print(f"\n📦 Package sélectionné: {selected_pkg['client_name']}")
    print(f"   Statut actuel: {selected_pkg['status']}")
    print()
    
    # Afficher les options de statut
    print("=" * 60)
    print("📊 STATUTS DISPONIBLES")
    print("=" * 60)
    print()
    
    status_options = {
        1: PackageStatus.IN_STOCK,
        2: PackageStatus.PLANNED,
        3: PackageStatus.DELIVERY_IN_PROGRESS,
        4: PackageStatus.DELIVERED_SUCCESSFULLY,
        5: PackageStatus.DELIVERY_FAILURE,
    }
    
    status_icons = {
        PackageStatus.IN_STOCK: "📥",
        PackageStatus.PLANNED: "📋",
        PackageStatus.DELIVERY_IN_PROGRESS: "🚚",
        PackageStatus.DELIVERED_SUCCESSFULLY: "✅",
        PackageStatus.DELIVERY_FAILURE: "❌",
    }
    
    for i, status in status_options.items():
        icon = status_icons.get(status, "📦")
        print(f"  [{i}] {icon} {status.value}")
    
    print()
    
    # Demander le nouveau statut
    while True:
        try:
            choice = input("Choisissez le nouveau statut (1-5) ou 0 pour annuler: ").strip()
            status_index = int(choice)
            
            if status_index == 0:
                print("❌ Annulé")
                return
            
            if status_index in status_options:
                break
            
            print("❌ Veuillez entrer un nombre entre 1 et 5")
        except ValueError:
            print("❌ Entrée invalide, veuillez entrer un nombre")
    
    new_status = status_options[status_index]
    
    # Confirmation
    print()
    print(f"🔄 Mise à jour du package {selected_pkg['client_name']}:")
    print(f"   Ancien statut: {selected_pkg['status']}")
    print(f"   Nouveau statut: {new_status.value}")
    print()
    
    confirm = input("Confirmer la mise à jour ? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Annulé")
        return
    
    # Mettre à jour le package
    http = HttpRequestServices()
    crud = CrudService(http)
    
    try:
        token = await token_manager.get_valid_token(http)
        if not token:
            print("❌ Impossible d'obtenir un token valide")
            return False
        
        http.set_token(token)
        
        # Récupérer le package complet
        package = await crud.get_package_by_id(selected_pkg["package_id"])
        if not package:
            print("❌ Package non trouvé")
            return False
        
        old_status = package.status
        package.status = new_status
        success = await crud.update_package(selected_pkg["package_id"], package)
        
        if success:
            print(f"✅ Statut mis à jour: {old_status.value} → {new_status.value}")
            log_info(f"Package {selected_pkg['package_id']} mis à jour: {old_status.value} -> {new_status.value}")
            return True
        else:
            print("❌ Échec de la mise à jour")
            log_error(f"Échec de la mise à jour du package: {selected_pkg['package_id']}")
            return False
    
    except Exception as e:
        print(f"❌ Erreur: {e}")
        log_error(f"Exception lors de la mise à jour: {e}")
        return False
    
    finally:
        await http.close()


async def main():
    """Point d'entrée principal du CLI"""
    print("=" * 60)
    print("🚚 RYDLE DASHBOARD - Livraisons du jour")
    print("=" * 60)
    print()
    
    log_info("=" * 60)
    log_info("Démarrage du CLI - Récupération des livraisons")
    
    # Demander le numéro de série du driver
    driver_serial = input("Entrez votre numéro de série driver: ").strip()
    
    if not driver_serial:
        log_error("Numéro de série driver vide")
        print("❌ Le numéro de série ne peut pas être vide")
        return
    
    log_info(f"Driver serial number entré: {driver_serial}")
    
    # Demander si mode debug
    debug_mode = input("Mode debug ? (y/n): ").strip().lower() == 'y'
    print()
    
    if debug_mode:
        log_debug("Mode debug activé")
    
    # Créer le token manager (utilise token_cache.md dans le dossier courant)
    script_dir = Path(__file__).parent
    token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
    
    # Récupérer les livraisons
    deliveries = await get_driver_deliveries(
        driver_serial, 
        debug=debug_mode,
        token_manager=token_manager
    )
    
    if deliveries is None:
        log_error("Échec de la récupération des livraisons")
        print("\n❌ Échec de la récupération des livraisons")
        return
    
    if len(deliveries) == 0:
        log_info("Aucune livraison prévue pour aujourd'hui")
        print("\n✅ Aucune livraison prévue pour aujourd'hui")
        return
    
    # Afficher les résultats
    print()
    print("=" * 60)
    print(f"📋 RÉSUMÉ DES LIVRAISONS - {get_today_date()}")
    print("=" * 60)

    # Collecter tous les packages dans une liste plate
    all_packages = []
    total_packages = 0
    
    for i, delivery in enumerate(deliveries, 1):
        print(f"\n🚛 Tournée #{i}")
        print(f"   Véhicule: {delivery['vehicle_license_plate']}")
        print(f"   Nombre de colis: {delivery['total_packages']}")
        print()

        for j, pkg in enumerate(delivery["packages"], 1):
            fragile_mark = " 🧊" if pkg["is_fragile"] else ""
            print(f"   {j}. [{pkg['status']}] {pkg['client_name']}{fragile_mark}")
            print(f"      📍 {pkg['address']} {pkg['address_label'] or ''}")
            print(f"      📦 {pkg['weight']}kg / {pkg['volume']}m³")
            if pkg['description']:
                print(f"      ℹ️  {pkg['description']}")
            print()
            
            # Ajouter à la liste pour mise à jour
            all_packages.append(pkg)
        
        total_packages += delivery["total_packages"]

    print("=" * 60)
    print(f"📊 Total: {len(deliveries)} tournée(s), {total_packages} colis à livrer")
    print("=" * 60)

    # Proposer de mettre à jour un package
    while True:
        print()
        print("Options:")
        print("  [1] 🔄 Mettre à jour le statut d'un package")
        print("  [0] ❌ Quitter")
        print()
        
        choice = input("Votre choix: ").strip()
        
        if choice == "1":
            await update_package_status_cli(all_packages, token_manager)
            # Après mise à jour, rafraîchir l'affichage
            print("\n🔄 Actualisation des données...")
            deliveries = await get_driver_deliveries(
                driver_serial,
                debug=debug_mode,
                token_manager=token_manager
            )
            if deliveries:
                # Ré-afficher les livraisons avec les données à jour
                print()
                print("=" * 60)
                print(f"📋 RÉSUMÉ DES LIVRAISONS (actualisé) - {get_today_date()}")
                print("=" * 60)
                
                all_packages = []
                for i, delivery in enumerate(deliveries, 1):
                    print(f"\n🚛 Tournée #{i}")
                    print(f"   Véhicule: {delivery['vehicle_license_plate']}")
                    print(f"   Nombre de colis: {delivery['total_packages']}")
                    print()

                    for j, pkg in enumerate(delivery["packages"], 1):
                        fragile_mark = " 🧊" if pkg["is_fragile"] else ""
                        print(f"   {j}. [{pkg['status']}] {pkg['client_name']}{fragile_mark}")
                        print(f"      📍 {pkg['address']} {pkg['address_label'] or ''}")
                        print(f"      📦 {pkg['weight']}kg / {pkg['volume']}m³")
                        if pkg['description']:
                            print(f"      ℹ️  {pkg['description']}")
                        print()
                        
                        all_packages.append(pkg)
                
                print("=" * 60)
                print(f"📊 Total: {len(deliveries)} tournée(s), {sum(d['total_packages'] for d in deliveries)} colis à livrer")
                print("=" * 60)
        elif choice == "0":
            break
        else:
            print("❌ Choix invalide")

    log_info("=" * 60)
    log_info("Fin du CLI - Succès")


if __name__ == "__main__":
    asyncio.run(main())
