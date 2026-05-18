from dataclasses import dataclass
from typing import Optional


@dataclass
class Address:
    id: Optional[str] = None
    label: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
