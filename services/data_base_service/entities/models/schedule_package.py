from dataclasses import dataclass
from typing import Optional


@dataclass
class SchedulePackage:
    id: Optional[str] = None
    schedule_id: str = ""
    package_id: str = ""
    position: Optional[int] = None
