#!/usr/bin/env python3
"""
CLI - Mettre à jour le statut d'un package
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
)
from entities.models import Package
from entities.enum.package_status import PackageStatus


async def get_planned_packages(token_manager: TokenManager) -> Optional[list[Package]]:
    """
    Récupère uniquement les packages avec le statut 'planned' depuis l'API.
    
    Returns:
        Liste des packages planned ou None si erreur
    """
    http = HttpRequestServices()
    crud = CrudService(http)
    
    try:
        # Obtenir un token valide
        print("🔐 Vérification du token...")
        token = await token_manager.get_valid_token(http)
        
        if not token:
            log_error("Impossible d'obtenir un token valide")
            print("❌ Impossible d'obtenir un token valide")
            return None
        
        http.set_token(token)
        
        # Récupérer uniquement les packages 'planned'
        log_info("Récupération des packages avec statut 'planned'")
        print("📦 Récupération des packages à planifier...")
        packages = await crud.get_all_package(status_filter=PackageStatus.PLANNED)
        
        log_success(f"{len(packages)} package(s) récupéré(s)")
        return packages
        
    except Exception as e:
        log_error(f"Exception lors de la récupération des packages: {e}")
        print(f"❌ Erreur: {e}")
        return None
    finally:
        await http.close()


async def update_package_status(
    package_id: str, 
    new_status: PackageStatus,
    token_manager: TokenManager
) -> bool:
    """
    Met à jour le statut d'un package.
    
    Args:
        package_id: ID du package à mettre à jour
        new_status: Nouveau statut
        token_manager: Gestionnaire de token
        
    Returns:
        True si la mise à jour a réussi
    """
    http = HttpRequestServices()
    crud = CrudService(http)
    
    try:
        # Obtenir un token valide
        token = await token_manager.get_valid_token(http)
        
        if not token:
            log_error("Impossible d'obtenir un token valide")
            return False
        
        http.set_token(token)
        
        # Récupérer le package actuel
        log_info(f"Récupération du package: {package_id}")
        package = await crud.get_package_by_id(package_id)
        
        if not package:
            log_error(f"Package non trouvé: {package_id}")
            print(f"❌ Package non trouvé: {package_id}")
            return False
        
        old_status = package.status
        log_info(f"Package actuel: {package.client_name} - Statut: {old_status.value}")
        
        # Mettre à jour le statut
        package.status = new_status
        log_info(f"Mise à jour du statut: {old_status.value} -> {new_status.value}")
        
        success = await crud.update_package(package_id, package)
        
        if success:
            log_success(f"Package {package_id} mis à jour: {old_status.value} -> {new_status.value}")
            print(f"✅ Statut mis à jour: {old_status.value} → {new_status.value}")
        else:
            log_error(f"Échec de la mise à jour du package: {package_id}")
            print("❌ Échec de la mise à jour")
        
        return success
        
    except Exception as e:
        log_error(f"Exception lors de la mise à jour: {e}")
        print(f"❌ Erreur: {e}")
        return False
    finally:
        await http.close()


def display_packages(packages: list[Package]):
    """Affiche la liste des packages"""
    print()
    print("=" * 70)
    print("📦 LISTE DES PACKAGES")
    print("=" * 70)
    print()
    
    if not packages:
        print("Aucun package trouvé")
        return
    
    # Afficher les packages avec index
    for i, pkg in enumerate(packages, 1):
        status_icon = {
            PackageStatus.IN_STOCK: "📥",
            PackageStatus.PLANNED: "📋",
            PackageStatus.DELIVERY_IN_PROGRESS: "🚚",
            PackageStatus.DELIVERED_SUCCESSFULLY: "✅",
            PackageStatus.DELIVERY_FAILURE: "❌",
        }.get(pkg.status, "📦")
        
        fragile_mark = " 🧊" if pkg.is_fragile else ""
        address_label = f" ({pkg.address_label})" if pkg.address_label else ""
        
        print(f"  [{i:2d}] {status_icon} {pkg.client_name}{fragile_mark}")
        print(f"       📍 {pkg.address}{address_label}")
        print(f"       📊 Statut: {pkg.status.value}")
        print(f"       📅 Livraison: {pkg.delivery_date.strftime('%Y-%m-%d')}")
        print()


def display_status_options() -> dict[int, PackageStatus]:
    """Affiche les options de statut et retourne un mapping index -> status"""
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


async def main():
    """Point d'entrée principal du CLI"""
    print("=" * 70)
    print("🚚 RYDLE DASHBOARD - Mise à jour du statut d'un package")
    print("=" * 70)
    print()
    
    log_info("=" * 70)
    log_info("Démarrage du CLI - Mise à jour de statut package")
    
    # Créer le token manager
    script_dir = Path(__file__).parent
    token_manager = TokenManager(cache_file=script_dir / "token_cache.md")
    
    # Étape 1: Récupérer uniquement les packages 'planned'
    packages = await get_planned_packages(token_manager)
    
    if packages is None or len(packages) == 0:
        print("\n❌ Aucun package à afficher")
        return
    
    # Étape 2: Afficher les packages
    print()
    print("=" * 70)
    print("📦 PACKAGES À PLANIFIER (statut: planned)")
    print("=" * 70)
    display_packages(packages)
    
    # Étape 3: Demander à l'utilisateur de choisir un package
    while True:
        try:
            choice = input(f"Choisissez un package (1-{len(packages)}) ou 0 pour annuler: ").strip()
            package_index = int(choice)
            
            if package_index == 0:
                print("❌ Annulé")
                return
            
            if 1 <= package_index <= len(packages):
                break
            
            print(f"❌ Veuillez entrer un nombre entre 1 et {len(packages)}")
        except ValueError:
            print("❌ Entrée invalide, veuillez entrer un nombre")
    
    selected_package = packages[package_index - 1]
    print(f"\n📦 Package sélectionné: {selected_package.client_name}")
    print(f"   Statut actuel: {selected_package.status.value}")
    print()
    
    # Étape 4: Afficher les options de statut
    status_options = display_status_options()
    
    # Étape 5: Demander le nouveau statut
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
    print(f"🔄 Mise à jour du package {selected_package.client_name}:")
    print(f"   Ancien statut: {selected_package.status.value}")
    print(f"   Nouveau statut: {new_status.value}")
    print()
    
    confirm = input("Confirmer la mise à jour ? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("❌ Annulé")
        return
    
    # Étape 6: Mettre à jour le package
    print()
    success = await update_package_status(selected_package.id, new_status, token_manager)
    
    if success:
        log_info("=" * 70)
        log_info("Mise à jour du statut terminée avec succès")
    else:
        log_error("=" * 70)
        log_error("Échec de la mise à jour du statut")


if __name__ == "__main__":
    asyncio.run(main())
