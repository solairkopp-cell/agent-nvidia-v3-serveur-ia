from enum import Enum


class DispatchStep(Enum):
    PLANNING = "planning"
    PACKAGES = "packages"
    RESOURCES = "resources"
