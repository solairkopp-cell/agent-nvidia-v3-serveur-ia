from dataclasses import dataclass
from typing import Optional


@dataclass
class DeliveryFailure:
    id: Optional[str] = None
    package_id: str = ""
    cause: int = 0  # 1-6
    comment: str = ""
