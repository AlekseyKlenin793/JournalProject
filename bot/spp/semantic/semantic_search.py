import numpy as np
from typing import Dict, List

from .model import get_model


def encode_query(query: str) -> np.ndarray:
    model = get_model()
    embedding = model.encode(
        "query: " + query,
        normalize_embeddings=True
    )
    return embedding


def cosine_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return 0.0

    v1 = np.array(vec1)
    v2 = np.array(vec2)

    if np.linalg.norm(v1) == 0 or np.linalg.norm(v2) == 0:
        return 0.0

    return float(np.dot(v1, v2))


def get_semantic_scores(journals: List, query: str) -> Dict[int, float]:
    query_embedding = encode_query(query)

    scores = {}

    for journal in journals:
        emb = getattr(journal, "embedding", None)

        if emb is None:
            scores[journal.id] = 0.0
            continue

        score = cosine_similarity(query_embedding, emb)
        scores[journal.id] = score

    return scores