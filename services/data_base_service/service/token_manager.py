import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path
import json

from .logger_service import log_info, log_error, log_debug, log_success


class TokenManager:
    """Gère le cache du token d'authentification avec validité 24h"""
    
    BASE_URL = "https://v2.fleet.akkurad-engineering.com/api/"
    
    # Credentials from Flutter project
    EMAIL = "n.baldi22412@pi.tn"
    PASSWORD = "12345678"
    
    def __init__(self, cache_file: str = "token_cache.md"):
        self.cache_file = Path(cache_file)
        self._token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
    
    def load_cache(self) -> bool:
        """
        Charge le token depuis le fichier cache.
        
        Returns:
            True si un token valide est trouvé, False sinon
        """
        try:
            if not self.cache_file.exists():
                log_debug("Aucun fichier de cache token trouvé")
                return False
            
            content = self.cache_file.read_text(encoding='utf-8')
            
            # Parser le fichier markdown
            for line in content.split('\n'):
                if line.startswith('**Token:**'):
                    self._token = line.replace('**Token:**', '').strip()
                elif line.startswith('**Expires:**'):
                    expires_str = line.replace('**Expires:**', '').strip()
                    self._expires_at = datetime.fromisoformat(expires_str)
            
            # Vérifier si le token est encore valide
            if self._token and self._expires_at:
                if datetime.now() < self._expires_at:
                    log_success(f"Token valide jusqu'au {self._expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    return True
                else:
                    log_warning(f"Token expiré depuis le {self._expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    return False
            
            return False
            
        except Exception as e:
            log_error(f"Erreur lors de la lecture du cache: {e}")
            return False
    
    def save_cache(self, token: str, validity_hours: int = 24) -> bool:
        """
        Sauvegarde le token dans le fichier cache.
        
        Args:
            token: Le token à sauvegarder
            validity_hours: Durée de validité en heures (défaut: 24)
            
        Returns:
            True si la sauvegarde a réussi, False sinon
        """
        try:
            self._token = token
            self._expires_at = datetime.now() + timedelta(hours=validity_hours)
            
            content = f"""# Token Cache - Fleet API

**Token:** {token}

**Expires:** {self._expires_at.isoformat()}

**Created:** {datetime.now().isoformat()}

**Validity:** {validity_hours} hours
"""
            
            self.cache_file.write_text(content, encoding='utf-8')
            log_success(f"Token sauvegardé (valide jusqu'au {self._expires_at.strftime('%Y-%m-%d %H:%M:%S')})")
            return True
            
        except Exception as e:
            log_error(f"Erreur lors de la sauvegarde du token: {e}")
            return False
    
    def get_token(self) -> Optional[str]:
        """Retourne le token actuel"""
        return self._token
    
    def is_valid(self) -> bool:
        """Vérifie si le token actuel est encore valide"""
        if not self._token or not self._expires_at:
            return False
        return datetime.now() < self._expires_at
    
    async def fetch_new_token(self, http_service) -> Optional[str]:
        """
        Récupère un nouveau token depuis l'API Fleet.
        
        Args:
            http_service: Instance de HttpRequestServices
            
        Returns:
            Le nouveau token ou None si échec
        """
        try:
            log_info("Tentative de connexion à l'API Fleet...")
            url = f"{self.BASE_URL}auth/login"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    "email": self.EMAIL,
                    "password": self.PASSWORD
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        token_data = data.get("token", {})
                        token = token_data.get("accessToken")
                        
                        if token:
                            log_success("Authentification réussie auprès de l'API Fleet")
                            self.save_cache(token)
                            return token
                        else:
                            log_error("Token non présent dans la réponse de l'API")
                    else:
                        log_error(f"Échec de l'authentification - Status HTTP: {response.status}")
                
                log_error("Échec de la récupération du token")
                return None
                
        except Exception as e:
            log_error(f"Exception lors de la récupération du token: {e}")
            return None
    
    async def get_valid_token(self, http_service) -> Optional[str]:
        """
        Retourne un token valide, depuis le cache ou en le rafraîchissant.
        
        Args:
            http_service: Instance de HttpRequestServices
            
        Returns:
            Un token valide ou None si échec
        """
        # Essayer de charger depuis le cache
        if self.load_cache() and self._token:
            return self._token
        
        # Fetch un nouveau token
        log_info("Token non valide ou absent, récupération d'un nouveau token...")
        return await self.fetch_new_token(http_service)
