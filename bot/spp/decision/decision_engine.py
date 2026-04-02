from typing import List, Tuple
from ..criteria.criteria_model import Criterion
from ..scoring.normalization import collect_statistics
from ..scoring.base_score import calculate_journal_score

# НОВОЕ
from ..semantic.semantic_search import get_semantic_scores


def rank_journals(
    journals: List,
    criteria: List[Criterion],
    query: str = None,
    alpha: float = 0.7,
    top_n: int = 10
) -> List[Tuple]:

    if not journals:
        return []

    stats = collect_statistics(journals, criteria)

    # --- классический скор ---
    classical_scores = {}
    for journal in journals:
        score = calculate_journal_score(
            journal=journal,
            criteria=criteria,
            stats=stats
        )
        classical_scores[journal.id] = score

    # --- семантический скор ---
    semantic_scores = {}
    if query:
        semantic_scores = get_semantic_scores(journals, query)

    scored_journals = []

    for journal in journals:
        classical = classical_scores.get(journal.id, 0.0)
        semantic = semantic_scores.get(journal.id, 0.0)

        # гибрид
        final_score = (1 - alpha) * classical + alpha * semantic

        scored_journals.append((journal, round(final_score, 4)))

    scored_journals.sort(key=lambda x: x[1], reverse=True)

    return scored_journals[:top_n]