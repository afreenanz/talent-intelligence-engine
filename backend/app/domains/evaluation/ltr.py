"""LambdaMART (LightGBM) training, isolated in a separate process.

Why a separate process: on macOS, PyTorch bundles its own OpenMP runtime and LightGBM links
Homebrew's libomp. Loading both in one process crashed (SIGSEGV when torch loaded first) or
deadlocked (when LightGBM loaded first), as reproduced on 2026-11-17. The worker below
imports only numpy and LightGBM, and receives plain arrays, so the two runtimes never meet.
"""

from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import numpy as np
import numpy.typing as npt

Matrix = npt.NDArray[np.float64]


def _loqo_worker(
    data: list[tuple[str, Matrix, npt.NDArray[np.int64]]], seed: int
) -> dict[str, list[float]]:
    import lightgbm  # imported only inside the clean worker process

    out: dict[str, list[float]] = {}
    for held, x_held, _ in data:
        train = [(x, y) for q, x, y in data if q != held]
        model = lightgbm.LGBMRanker(
            objective="lambdarank",
            n_estimators=100,
            learning_rate=0.05,
            num_leaves=7,
            min_child_samples=10,
            random_state=seed,
            deterministic=True,
            n_jobs=1,
            verbose=-1,
        )
        model.fit(
            np.vstack([x for x, _ in train]),
            np.concatenate([y for _, y in train]),
            group=[len(y) for _, y in train],
        )
        out[held] = np.asarray(model.predict(x_held), dtype=float).tolist()
    return out


def lambdamart_leave_one_query_out(
    data: list[tuple[str, Matrix, npt.NDArray[np.int64]]], seed: int = 0
) -> dict[str, list[float]]:
    """data = [(query_id, features[n_docs, n_features], labels[n_docs])].

    Returns held-out scores per query."""
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
        return pool.submit(_loqo_worker, data, seed).result()
