from .criteria_model import Criterion, CriterionType

# Базовый набор критериев СППР
DEFAULT_CRITERIA = [
    Criterion(
        name="Категория журнала",
        field="final_category",
        criterion_type=CriterionType.MAX,
        weight=0.15,
        description="Категория журнала (К1 > К2 > К3)"
    ),
    Criterion(
        name="Индекс Хирша",
        field="h_index",
        criterion_type=CriterionType.MAX,
        weight=0.25,
        description="Научная значимость журнала"
    ),
    Criterion(
        name="Индекс цитирования",
        field="citation_index",
        criterion_type=CriterionType.MAX,
        weight=0.15,
        description="Средний уровень цитируемости"
    ),
    Criterion(
        name="Белый список",
        field="white_list_level_2025",
        criterion_type=CriterionType.MAX,
        weight=0.20,
        description="Наличие и уровень в белом списке"
    ),
    Criterion(
        name="Цена публикации",
        field="publication_price",
        criterion_type=CriterionType.MIN,
        weight=0.15,
        description="Стоимость публикации статьи"
    ),
    Criterion(
        name="Время публикации",
        field="publication_time_value",
        criterion_type=CriterionType.MIN,
        weight=0.10,
        description="Ожидаемое время публикации"
    ),
]
