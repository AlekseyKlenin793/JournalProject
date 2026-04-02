from typing import List, Dict, Tuple
from ..criteria.criteria_model import Criterion

CATEGORY_MAPPING = {
    "К1": 3,
    "К2": 2,
    "К3": 1
}


def normalize_raw_value(field: str, value):
    if value is None:
        return None

    if field == "final_category":
        return CATEGORY_MAPPING.get(value)

    return value


def collect_statistics(journals: List, criteria: List[Criterion]) -> Dict[str, Tuple[float, float]]:
    stats = {}

    for criterion in criteria:
        field = criterion.field
        values = []

        for journal in journals:
            raw_value = getattr(journal, field, None)
            normalized_value = normalize_raw_value(field, raw_value)

            if normalized_value is not None:
                values.append(normalized_value)

        if values:
            stats[field] = (min(values), max(values))
        else:
            stats[field] = (None, None)

    return stats
