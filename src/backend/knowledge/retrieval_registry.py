from __future__ import annotations

from src.backend.knowledge.retrieval_strategy import BaselineHybridRagStrategy, RetrievalStrategy


_STRATEGIES: dict[str, RetrievalStrategy] = {}


def register_retrieval_strategy(strategy: RetrievalStrategy) -> RetrievalStrategy:
    _STRATEGIES[str(strategy.name).strip().lower()] = strategy
    return strategy


def get_retrieval_strategy(name: str) -> RetrievalStrategy:
    normalized = str(name or "").strip().lower() or "baseline_hybrid"
    strategy = _STRATEGIES.get(normalized)
    if strategy is None:
        raise KeyError(f"Unknown retrieval strategy: {name}")
    return strategy


def list_retrieval_strategies() -> tuple[str, ...]:
    return tuple(sorted(_STRATEGIES))


register_retrieval_strategy(BaselineHybridRagStrategy())


__all__ = ["get_retrieval_strategy", "list_retrieval_strategies", "register_retrieval_strategy"]
