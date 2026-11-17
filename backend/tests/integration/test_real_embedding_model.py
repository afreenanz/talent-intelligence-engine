"""Uses the real configured model (~130 MB download on first run; cached afterwards)."""

import numpy as np
import pytest

from app.integrations.embeddings.base import KNOWN_MODELS
from app.integrations.embeddings.sentence_transformer import SentenceTransformerEmbedder

pytestmark = pytest.mark.model


@pytest.fixture(scope="module")
def bge() -> SentenceTransformerEmbedder:
    return SentenceTransformerEmbedder(KNOWN_MODELS["BAAI/bge-small-en-v1.5"])


def test_vectors_are_normalised_384d(bge: SentenceTransformerEmbedder) -> None:
    v = bge.encode_documents(["Backend engineer"])
    assert v.shape == (1, 384)
    assert np.linalg.norm(v[0]) == pytest.approx(1.0, abs=1e-4)


def test_query_prefix_is_applied(bge: SentenceTransformerEmbedder) -> None:
    as_query = bge.encode_queries(["python jobs"])[0]
    as_doc = bge.encode_documents(["python jobs"])[0]
    assert not np.allclose(as_query, as_doc)  # the instruction prefix changes the query vector


def test_semantics_beyond_keywords(bge: SentenceTransformerEmbedder) -> None:
    q = bge.encode_queries(["people who build data pipelines"])[0]
    docs = bge.encode_documents(
        [
            "Data Engineer: build and maintain batch and streaming ETL with Spark and Airflow.",
            "Frontend Engineer: build responsive React interfaces and design systems.",
        ]
    )
    data, frontend = docs @ q
    assert data > frontend + 0.05
