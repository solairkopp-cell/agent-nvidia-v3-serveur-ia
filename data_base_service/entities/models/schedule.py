from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Schedule:
    id: Optional[str] = None
    delivery_date: datetime = None
    driver_serial_number: str = ""
    vehicle_license_plate: str = ""

    def __post_init__(self):
        if self.delivery_date is None:
            self.delivery_date = datetime.now()
