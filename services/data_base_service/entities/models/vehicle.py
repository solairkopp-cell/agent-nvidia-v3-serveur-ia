from dataclasses import dataclass
from typing import Optional


@dataclass
class Vehicle:
    id: Optional[str] = None
    license_plate: str = ""
    brand: str = ""
    weight_capacity: float = 0.0
    volume_capacity: float = 0.0
