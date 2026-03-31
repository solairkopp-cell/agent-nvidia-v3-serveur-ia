from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class DriverAvailability:
    id: Optional[str] = None
    driver_id: str = ""
    available_date: datetime = None

    def __post_init__(self):
        if self.available_date is None:
            self.available_date = datetime.now()
