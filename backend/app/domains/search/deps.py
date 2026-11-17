from typing import Annotated

from fastapi import Depends

from app.integrations.embeddings.base import Embedder
from app.integrations.embeddings.sentence_transformer import get_embedder


def embedder_dependency() -> Embedder:
    return get_embedder()


EmbedderDep = Annotated[Embedder, Depends(embedder_dependency)]
