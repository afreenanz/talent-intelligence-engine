from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.domains.ranking.cross_encoder import Reranker, get_cross_encoder
from app.domains.ranking.weighted import WeightedRanker


@lru_cache
def _ranker() -> WeightedRanker:
    return WeightedRanker.from_file()


def ranker_dependency() -> WeightedRanker:
    return _ranker()


def reranker_provider_dependency() -> Callable[[], Reranker]:
    # A provider, not the model itself: the ~90 MB cross-encoder is loaded only when a request
    # actually asks for stage 2.
    return get_cross_encoder


RankerDep = Annotated[WeightedRanker, Depends(ranker_dependency)]
RerankerProviderDep = Annotated[Callable[[], Reranker], Depends(reranker_provider_dependency)]
