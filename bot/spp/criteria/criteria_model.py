from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CriterionType(Enum):
    MAX = "max"
    MIN = "min"
    BINARY = "binary"


@dataclass
class Criterion:
    name: str
    field: str
    criterion_type: CriterionType
    weight: float
    description: Optional[str] = None
