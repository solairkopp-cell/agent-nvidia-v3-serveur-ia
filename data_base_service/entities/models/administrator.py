from dataclasses import dataclass
from typing import Optional


@dataclass
class Administrator:
    id: Optional[str] = None
    serial_number: str = ""
    name: str = ""
