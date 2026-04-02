from sentence_transformers import SentenceTransformer

# Singleton модель (загружается 1 раз)
_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("intfloat/multilingual-e5-base")
    return _model