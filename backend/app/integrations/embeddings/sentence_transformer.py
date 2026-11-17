from functools import lru_cache

import numpy as np
import structlog

from app.core.config import get_settings
from app.integrations.embeddings.base import KNOWN_MODELS, ModelSpec, Vector

log = structlog.get_logger(__name__)


class SentenceTransformerEmbedder:
    """Local Sentence Transformers model. Vectors are L2-normalised, so cosine = dot product."""

    def __init__(self, spec: ModelSpec, device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, deferred

        self._spec = spec
        self._model = SentenceTransformer(spec.name, device=device)
        actual = self._model.get_embedding_dimension()
        if actual != spec.dimension:
            raise ValueError(f"{spec.name} produces {actual}-d vectors, expected {spec.dimension}")

    @property
    def spec(self) -> ModelSpec:
        return self._spec

    def encode_queries(self, texts: list[str]) -> Vector:
        return self._encode([self._spec.query_prefix + t for t in texts], batch_size=32)

    def encode_documents(self, texts: list[str], batch_size: int = 64) -> Vector:
        return self._encode([self._spec.document_prefix + t for t in texts], batch_size)

    def _encode(self, texts: list[str], batch_size: int) -> Vector:
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)


@lru_cache
def get_embedder() -> SentenceTransformerEmbedder:
    """One model instance per process (loading takes ~10 s; it is reused for every request)."""
    settings = get_settings()
    spec = KNOWN_MODELS.get(settings.embedding_model)
    if spec is None:
        raise ValueError(
            f"Unknown EMBEDDING_MODEL {settings.embedding_model!r}; add it to KNOWN_MODELS"
        )
    log.info("embedding_model_loading", model=spec.name, device=settings.embedding_device)
    return SentenceTransformerEmbedder(spec, device=settings.embedding_device)
