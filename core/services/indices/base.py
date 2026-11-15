"""Base class for deterministic index calculators with a reserved agent seam."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.services.contracts import IndexContext, IndexEvaluationResult


class BaseIndexProvider(ABC):
    index_id = "BASE"
    version = "1.0"
    agent_hook = None

    def compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        result = self._compute(ctx)
        hook = self.agent_hook
        if hook is not None and getattr(hook, "enabled", False):
            result = hook.modify(result, ctx)
        return result

    @abstractmethod
    def _compute(self, ctx: IndexContext) -> IndexEvaluationResult:
        raise NotImplementedError
