import aiohttp
from typing import Optional, Dict, Any


class AuthentificationService:
    """Service d'authentification pour Fleet API"""
    
    BASE_URL = "https://v2.fleet.akkurad-engineering.com/api/"
    
    # Credentials from Flutter project
    EMAIL = "n.baldi22412@pi.tn"
    PASSWORD = "12345678"
    
    def __init__(self, http_service):
        self.http = http_service
    
    async def connect(self) -> bool:
        """
        Se connecte à l'API Fleet et récupère un token d'authentification.
        
        Returns:
            True si la connexion a réussi, False sinon
        """
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
                        self.http.set_token(token)
                        print("✅ Authentification réussie")
                        return True
                
                print("❌ Échec de l'authentification")
                return False
