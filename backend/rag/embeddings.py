from threading import Lock

from fastembed import TextEmbedding


MODEL_NAME = "BAAI/bge-small-en-v1.5"
VECTOR_DIMENSIONS = 384

_embedding_model: TextEmbedding | None = None
_embedding_lock = Lock()


def _get_model() -> TextEmbedding:
    global _embedding_model
    with _embedding_lock:
        if _embedding_model is None:
            _embedding_model = TextEmbedding(model_name=MODEL_NAME)
        return _embedding_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = _get_model()
    with _embedding_lock:
        vectors = [vector.tolist() for vector in model.embed(texts)]

    if any(len(vector) != VECTOR_DIMENSIONS for vector in vectors):
        raise RuntimeError(
            f"Embedding model {MODEL_NAME} returned an unexpected vector dimension."
        )
    return vectors


def embed_query(query: str) -> list[float]:
    vectors = embed_texts([query])
    return vectors[0]
