from typing import List
from ..criteria.criteria_model import Criterion, CriterionType
from ..scoring.normalization import normalize_raw_value


def safe_float(value):
    """
    Безопасное приведение значений из БД (Decimal, int, None) к float
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_value(value, min_value, max_value, criterion_type):
    """
    Нормализация значения в диапазон [0;1]
    """
    value = safe_float(value)
    min_value = safe_float(min_value)
    max_value = safe_float(max_value)

    if value is None or min_value is None or max_value is None:
        return 0.0

    if max_value == min_value:
        return 1.0

    if criterion_type == CriterionType.MAX:
        return (value - min_value) / (max_value - min_value)

    if criterion_type == CriterionType.MIN:
        return (max_value - value) / (max_value - min_value)

    return 0.0


def calculate_journal_score(journal, criteria: List[Criterion], stats: dict):
    """
    Расчёт итогового балла журнала по всем критериям
    """
    total_score = 0.0

    for criterion in criteria:
        field = criterion.field
        raw_value = getattr(journal, field, None)
        raw_value = normalize_raw_value(field, raw_value)

        min_val, max_val = stats.get(field, (None, None))

        normalized = normalize_value(
            raw_value,
            min_val,
            max_val,
            criterion.criterion_type
        )

        weighted_score = normalized * float(criterion.weight)
        total_score += weighted_score

    return round(total_score, 4)
