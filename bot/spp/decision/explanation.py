from typing import Dict, List
from ..criteria.criteria_model import Criterion
from ..scoring.normalization import normalize_raw_value
from ..scoring.base_score import normalize_value


def explain_journal_score(
    journal,
    criteria: List[Criterion],
    stats: Dict,
    semantic_score: float = 0.0,
    alpha: float = 0.4
) -> Dict:

    explanation = {
        "total_score": 0.0,
        "semantic_score": round(semantic_score, 4),
        "criteria": {}
    }

    classical_total = 0.0

    for criterion in criteria:
        field = criterion.field

        raw_value = getattr(journal, field, None)
        prepared_value = normalize_raw_value(field, raw_value)

        min_val, max_val = stats.get(field, (None, None))

        normalized = normalize_value(
            prepared_value,
            min_val,
            max_val,
            criterion.criterion_type
        )

        weighted_score = normalized * criterion.weight

        explanation["criteria"][criterion.name] = {
            "raw_value": raw_value,
            "normalized_value": round(normalized, 4),
            "weight": criterion.weight,
            "weighted_score": round(weighted_score, 4)
        }

        classical_total += weighted_score

    # гибридный итог
    total = (1 - alpha) * classical_total + alpha * semantic_score

    explanation["total_score"] = round(total, 4)

    return explanation