from enum import Enum


class PackageStatus(Enum):
    IN_STOCK = "in_stock"
    PLANNED = "planned"
    DELIVERY_IN_PROGRESS = "in_progress_delivery"
    DELIVERED_SUCCESSFULLY = "delivered_successfully"
    DELIVERY_FAILURE = "delivery_failure"
