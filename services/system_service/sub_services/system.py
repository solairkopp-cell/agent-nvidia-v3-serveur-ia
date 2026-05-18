import subprocess

class SystemService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemService, cls).__new__(cls)
        return cls._instance

    def execute(self, command: list):
        """Lance une commande système."""
        return subprocess.run(command, capture_output=True, text=True)

# Usage
system_service = SystemService()