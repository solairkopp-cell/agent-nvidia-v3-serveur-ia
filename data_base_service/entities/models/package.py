from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from ..enum.package_status import PackageStatus


@dataclass
class Package:
    id: Optional[str] = None
    client_name: str = ""
    address: str = ""
    address_label: Optional[str] = None
    weight: float = 0.0
    volume: float = 0.0
    description: str = ""
    delivery_date: datetime = None
    is_fragile: bool = False
    status: PackageStatus = PackageStatus.PLANNED

    def __post_init__(self):
        if self.delivery_date is None:
            from datetime import datetime
            self.delivery_date = datetime.now()
