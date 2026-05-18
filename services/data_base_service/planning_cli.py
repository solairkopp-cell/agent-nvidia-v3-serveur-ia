#!/usr/bin/env python3
"""
CLI - Interface interactive pour le Planning Service

Ce CLI utilise le PlanningService pour :
- Récupérer les livraisons d'un driver (trips)
- Mettre à jour le statut des packages
- Ajouter un échec de livraison
"""

import asyncio
from datetime import datetime
from pathlib import Path

from .service import (
    PlanningService,
    TokenManager,
    log_info,
    log_error,
)
from .entities.enum.package_status import PackageStatus


# Causes d'échec de livraison
DELIVERY_FAILURE_CAUSES = {
    1: "Destinataire absent",
    2: "Adresse incorrecte",
    3: "Colis endommagé",
    4: "Refus du destinataire",
    5: "Accès impossible",
    6: "Autre",
}


def get_today_date() -> str:
    """Retourne la date du jour au format YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def display_trips(trips: list):
    """Affiche les trips"""
    if not trips:
        print("Aucune livraison trouvée")
        return
    
    print()
    print("=" * 70)
    print(f"📋 LIVRAISONS - {get_today_date()}")
    print("=" * 70)
    
    for i, trip in enumerate(trips, 1):
        fragile_mark = " 🧊" if "Fragile" in (trip.get_package_info() or "") else ""
        
        print(f"\n  {i}. [{trip.get_delivery_status()}] {trip.get_client_name() or 'Client inconnu'}{fragile_mark}")
        print(f"       📍 {trip.get_name()}")
        if trip.get_package_info():
            print(f"       ℹ️  {trip.get_package_info()}")
    
    print()
    print("=" * 70)
    print(f"📊 Total: {len(trips)} colis à livrer")
    print("=" * 70)


def display_status_options() -> dict:
    """Affiche les options de statut"""
    print()
    print("=" * 70)
    print("📊 STATUTS DISPONIBLES")
    print("=" * 70)
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
    return status_options


async def update_package_interactive(service: PlanningService, trips: list):
    """Interface interactive pour mettre à jour un package"""
    if not trips:
        print("ℹ️  Aucun package à modifier")
        return
    
    # Afficher les trips
    print()
    print("=" * 70)
    print("📦 PACKAGES DISPONIBLES")
    print("=" * 70)
    print()
    
    for i, trip in enumerate(trips, 1):
        fragile_mark = " 🧊" if "Fragile" in (trip.get_package_info() or "") else ""
        
        print(f"  [{i:2d}] {trip.get_client_name() or 'Client inconnu'}{fragile_mark}")
        print(f"       📍 {trip.get_name()}")
        print(f"       📊 Statut: {trip.get_delivery_status()}")
        print()
    
    # Choisir un package
    while True:
        try:
            choice = input(f"Choisissez un package (1-{len(trips)}) ou 0 pour annuler: ").strip()
            package_index = int(choice)
            
            if package_index == 0:
                print("❌ Annulé")
                return
            
            if 1 <= package_index <= len(trips):
                break
            
            print(f"❌ Veuillez entrer un nombre entre 1 et {len(trips)}")
        except ValueError:
            print("❌ Entrée invalide")
    
    selected_trip = trips[package_index - 1]
    print(f"\n📦 Package sélectionné: {selected_trip.get_client_name()}")
    print(f"   Statut actuel: {selected_trip.get_delivery_status()}")
    
    # Choisir le nouveau statut
    status_options = display_status_options()
    
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
            print("❌ Entrée invalide")
    
    new_status = status_options[status_index]
    
    # Confirmation
    print()
    print(f"🔄 Mise à jour du package {selected_trip.get_client_name()}:")
    print(f"   Ancien statut: {selected_trip.get_delivery_status()}")
    print(f"   Nouveau statut: {new_status.value}")
    print()
    
    confirm = input("Confirmer ? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Annulé")
        return
    
    # Mettre à jour
    success = await service.update_package_status(selected_trip.get_id(), new_status)
    
    if success:
        print(f"✅ Statut mis à jour: {selected_trip.get_delivery_status()} → {new_status.value}")
    else:
        print("❌ Échec de la mise à jour")


async def add_delivery_failure_interactive(service: PlanningService, trips: list):
    """Interface interactive pour ajouter un échec de livraison"""
    if not trips:
        print("ℹ️  Aucun package pour signaler un échec")
        return
    
    # Afficher les trips
    print()
    print("=" * 70)
    print("📦 PACKAGES DISPONIBLES")
    print("=" * 70)
    print()
    
    for i, trip in enumerate(trips, 1):
        fragile_mark = " 🧊" if "Fragile" in (trip.get_package_info() or "") else ""
        
        print(f"  [{i:2d}] {trip.get_client_name() or 'Client inconnu'}{fragile_mark}")
        print(f"       📍 {trip.get_name()}")
        print(f"       📊 Statut: {trip.get_delivery_status()}")
        print()
    
    # Choisir un package
    while True:
        try:
            choice = input(f"Choisissez un package (1-{len(trips)}) ou 0 pour annuler: ").strip()
            package_index = int(choice)
            
            if package_index == 0:
                print("❌ Annulé")
                return
            
            if 1 <= package_index <= len(trips):
                break
            
            print(f"❌ Veuillez entrer un nombre entre 1 et {len(trips)}")
        except ValueError:
            print("❌ Entrée invalide")
    
    selected_trip = trips[package_index - 1]
    print(f"\n📦 Package sélectionné: {selected_trip.get_client_name()}")
    
    # Afficher les causes d'échec
    print()
    print("=" * 70)
    print("❌ CAUSES D'ÉCHEC DE LIVRAISON")
    print("=" * 70)
    print()
    
    for code, cause in DELIVERY_FAILURE_CAUSES.items():
        print(f"  [{code}] {cause}")
    
    print()
    
    # Choisir la cause
    while True:
        try:
            choice = input("Choisissez la cause (1-6) ou 0 pour annuler: ").strip()
            cause_index = int(choice)
            
            if cause_index == 0:
                print("❌ Annulé")
                return
            
            if cause_index in DELIVERY_FAILURE_CAUSES:
                break
            
            print("❌ Veuillez entrer un nombre entre 1 et 6")
        except ValueError:
            print("❌ Entrée invalide")
    
    cause = cause_index
    
    # Saisir le commentaire
    print()
    comment = input("Commentaire (décrivez l'échec): ").strip()
    
    if not comment:
        print("❌ Le commentaire ne peut pas être vide")
        return
    
    # Confirmation
    print()
    print(f"🔄 Signalement d'échec pour le package {selected_trip.get_client_name()}:")
    print(f"   Cause: [{cause}] {DELIVERY_FAILURE_CAUSES[cause]}")
    print(f"   Commentaire: {comment}")
    print()
    
    confirm = input("Confirmer ? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ Annulé")
        return
    
    # Ajouter l'échec
    success = await service.add_delivery_failure(selected_trip.get_id(), cause, comment)
    
    if success:
        print(f"✅ Échec de livraison enregistré")
        print(f"   Le statut du package a été mis à jour: planned → delivery_failure")
    else:
        print("❌ Échec de l'enregistrement")


async def main():
    """Point d'entrée principal"""
    print("=" * 70)
    print("🚚 RYDLE DASHBOARD - Gestion des livraisons")
    print("=" * 70)
    print()
    
    log_info("Démarrage du CLI Planning Service")
    
    # Demander le numéro de série
    driver_serial = input("Entrez votre numéro de série driver: ").strip()
    
    if not driver_serial:
        print("❌ Le numéro de série ne peut pas être vide")
        return
    
    # Initialiser le service
    script_dir = Path(__file__).parent
    token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
    service = PlanningService(token_manager)
    
    try:
        # Récupérer les trips (export JSON automatique)
        print()
        print("📦 Récupération des livraisons...")
        trips = await service.get_delivery_trips(driver_serial)
        
        if not trips:
            print("\n✅ Aucune livraison prévue pour aujourd'hui")
            return
        
        # Afficher les trips
        display_trips(trips)
        
        # Menu principal
        while True:
            print()
            print("Options:")
            print("  [1] 🔄 Mettre à jour le statut d'un package")
            print("  [2] ❌ Signaler un échec de livraison")
            print("  [3] 🔄 Actualiser les données")
            print("  [0] ❌ Quitter")
            print()
            
            choice = input("Votre choix: ").strip()
            
            if choice == "1":
                await update_package_interactive(service, trips)
                # Rafraîchir après mise à jour
                print("\n🔄 Actualisation des données...")
                trips = await service.get_delivery_trips(driver_serial)
                if trips:
                    display_trips(trips)
                else:
                    print("\n✅ Aucune livraison prévue pour aujourd'hui")
                    break
                    
            elif choice == "2":
                await add_delivery_failure_interactive(service, trips)
                # Rafraîchir après signalement
                print("\n🔄 Actualisation des données...")
                trips = await service.get_delivery_trips(driver_serial)
                if trips:
                    display_trips(trips)
                else:
                    print("\n✅ Aucune livraison prévue pour aujourd'hui")
                    break
                    
            elif choice == "3":
                print("\n🔄 Actualisation des données...")
                trips = await service.get_delivery_trips(driver_serial)
                if trips:
                    display_trips(trips)
                else:
                    print("\n✅ Aucune livraison prévue pour aujourd'hui")
                    break
                    
            elif choice == "0":
                print("👋 Au revoir !")
                break
            else:
                print("❌ Choix invalide")
    
    except Exception as e:
        print(f"❌ Erreur: {e}")
        log_error(f"Exception dans le CLI: {e}")
    
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
