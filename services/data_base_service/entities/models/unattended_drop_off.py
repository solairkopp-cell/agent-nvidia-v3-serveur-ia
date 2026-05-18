from dataclasses import dataclass
from typing import Optional


@dataclass
class UnattendedDropOff:
    id: Optional[str] = None
    package_id: str = ""
    drop_off_location: str = ""
    photo_path: str = ""
