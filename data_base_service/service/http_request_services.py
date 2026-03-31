import aiohttp
from typing import Optional, Dict, Any, List

from .logger_service import log_info, log_error, log_debug


class HttpRequestServices:
    BASE_URL = "https://v2.fleet.akkurad-engineering.com/api/"
    
    def __init__(self):
        self._token: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            log_debug("Session HTTP fermée")
    
    def set_token(self, token: str):
        self._token = token
        log_debug("Token défini pour les requêtes HTTP")
    
    def clear_token(self):
        self._token = None
        log_info("Token HTTP effacé")
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
    
    async def get_json(self, endpoint: str) -> Optional[Any]:
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"
            log_debug(f"GET {url}")
            
            async with session.get(url, headers=self._get_headers()) as response:
                if response.status == 200:
                    result = await response.json()
                    log_debug(f"GET {endpoint} - Succès")
                    return result
                else:
                    log_error(f"GET {endpoint} - Status: {response.status}")
                    return None
        except Exception as e:
            log_error(f"GET {endpoint} - Exception: {e}")
            return None
    
    async def post_json(self, endpoint: str, body: Dict[str, Any]) -> Optional[Any]:
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"
            log_debug(f"POST {url}")
            
            async with session.post(url, json=body, headers=self._get_headers()) as response:
                if response.status in (200, 201):
                    result = await response.json()
                    log_debug(f"POST {endpoint} - Succès")
                    return result
                else:
                    log_error(f"POST {endpoint} - Status: {response.status}")
                    return None
        except Exception as e:
            log_error(f"POST {endpoint} - Exception: {e}")
            return None
    
    async def put_json(self, endpoint: str, body: Dict[str, Any]) -> Optional[Any]:
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"
            log_debug(f"PUT {url}")
            
            async with session.put(url, json=body, headers=self._get_headers()) as response:
                if response.status == 200:
                    result = await response.json()
                    log_debug(f"PUT {endpoint} - Succès")
                    return result
                else:
                    log_error(f"PUT {endpoint} - Status: {response.status}")
                    return None
        except Exception as e:
            log_error(f"PUT {endpoint} - Exception: {e}")
            return None
    
    async def delete(self, endpoint: str) -> bool:
        try:
            session = await self._get_session()
            url = f"{self.BASE_URL}{endpoint}"
            log_debug(f"DELETE {url}")
            
            async with session.delete(url, headers=self._get_headers()) as response:
                success = response.status == 200
                if success:
                    log_debug(f"DELETE {endpoint} - Succès")
                else:
                    log_error(f"DELETE {endpoint} - Status: {response.status}")
                return success
        except Exception as e:
            log_error(f"DELETE {endpoint} - Exception: {e}")
            return False
    
    # Entity operations
    async def get_entity_instances(self, entity_id: str) -> Optional[List[Dict]]:
        log_info(f"Récupération des instances pour l'entité: {entity_id}")
        return await self.get_json(f"entity-instances/entity/{entity_id}")
    
    async def get_entity_instance_by_id(self, instance_id: str) -> Optional[Dict]:
        log_info(f"Récupération de l'instance: {instance_id}")
        return await self.get_json(f"entity-instances/{instance_id}")
    
    async def get_entity_instance_by_references(
        self, entity_id: str, field: str, value: str
    ) -> Optional[List[Dict]]:
        """
        Récupère les entités par référence.
        Utilise l'endpoint /entity-instances/by-reference/{referenceId}
        """
        log_info(f"Recherche par référence: field={field}, value={value}")
        # L'endpoint utilise la valeur de référence (driver.id, etc.)
        return await self.get_json(f"entity-instances/by-reference/{value}")
    
    async def create_entity_instance(self, entity_id: str, data: Dict[str, Any]) -> Optional[str]:
        log_info(f"Création d'une instance pour l'entité: {entity_id}")
        # Comme dans Flutter: {'data': data}
        result = await self.post_json(f"entity-instances/entity/{entity_id}", {'data': data})
        if result:
            log_success(f"Instance créée avec ID: {result.get('id')}")
        else:
            log_error(f"Échec de la création de l'instance pour l'entité: {entity_id}")
        return result.get("id") if result else None

    async def update_entity_instance(self, instance_id: str, data: Dict[str, Any]) -> bool:
        log_info(f"Mise à jour de l'instance: {instance_id}")
        # Comme dans Flutter: {'data': data}
        result = await self.put_json(f"entity-instances/{instance_id}", {'data': data})
        if result:
            log_success(f"Instance {instance_id} mise à jour")
        else:
            log_error(f"Échec de la mise à jour de l'instance: {instance_id}")
        return result is not None
    
    async def delete_entity_instance(self, instance_id: str) -> bool:
        log_info(f"Suppression de l'instance: {instance_id}")
        result = await self.delete(f"entity-instances/{instance_id}")
        if result:
            log_success(f"Instance {instance_id} supprimée")
        else:
            log_error(f"Échec de la suppression de l'instance: {instance_id}")
        return result
    
    async def search(self, entity_id: str, query: str) -> Optional[List[Dict]]:
        log_info(f"Recherche pour l'entité {entity_id}: query={query}")
        result = await self.get_json(f"entity-instances/entity/{entity_id}/search?query={query}")
        if result:
            log_debug(f"Résultat de la recherche: {result[:2] if len(result) > 2 else result}")
        return result
