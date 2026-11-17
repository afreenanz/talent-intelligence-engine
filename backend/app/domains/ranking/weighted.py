"""Stage 1: transparent weighted ranker.

    score = Σ_i w_i · f_i      (weights sum to 1, so score ∈ [0, 1])

Transparency is the point: each result's explanation is exactly its largest w_i·f_i terms,
so "why is this #1?" has a precise, reproducible answer.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from app.domains.ranking.features import FEATURE_NAMES, FeatureVector

DEFAULT_WEIGHTS = Path(__file__).with_name("weights_v1.json")


@dataclass(frozen=True)
class WeightedRanker:
    weights: dict[str, float]
    version: str

    def __post_init__(self) -> None:
        if set(self.weights) != set(FEATURE_NAMES):
            raise ValueError(f"weights must cover exactly {sorted(FEATURE_NAMES)}")
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be non-negative")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("weights must sum to 1")

    @classmethod
    def from_file(cls, path: Path = DEFAULT_WEIGHTS) -> "WeightedRanker":
        data = json.loads(path.read_text())
        return cls(weights=dict(data["weights"]), version=str(data["version"]))

    def contributions(self, fv: FeatureVector) -> dict[str, float]:
        return {name: self.weights[name] * fv.values[name] for name in FEATURE_NAMES}

    def score(self, fv: FeatureVector) -> float:
        return sum(self.contributions(fv).values())
