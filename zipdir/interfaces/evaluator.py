"""Interfaces and FactoryMethod metaclass for runtime path evaluation and 3-tier remapping."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.models import (
    DEvaluationResult,
    DIgnoreRule,
    MInterface,
    RuleKind,
)


class DEvaluationState:
    """Mutable state invariant accumulated across ancestor and target path evaluation."""

    is_excluded: bool
    shallowest_excluded_ancestor: PurePosixPath | None
    excluded_by: DIgnoreRule | None
    rescued_by: DIgnoreRule | None


class DRemapContext:
    """Data contract and invariant for 3-tier path remapping context."""

    rel_path: PurePosixPath
    rescued_by: DIgnoreRule
    shallowest_excluded_ancestor: PurePosixPath | None
    sub_path: PurePosixPath
    anchor_parent: PurePosixPath


class IRuleTransition:
    """Nominal Strategy interface for applying a matched rule to DEvaluationState."""

    def apply(
        self,
        state: DEvaluationState,
        rule: DIgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        raise NotImplementedError


class IRemapStrategy:
    """Nominal Strategy interface for resolving 3-tier destination archive paths."""

    def matches(self, target: str) -> bool:
        raise NotImplementedError

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
        raise NotImplementedError


class MPathEvaluator(MInterface):
    """FactoryMethod metaclass for IPathEvaluator."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPathEvaluator":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPathEvaluator:
    """State invariant for runtime path evaluators."""

    rules: tuple[DIgnoreRule, ...]
    transitions: Mapping[RuleKind, IRuleTransition]
    remap_strategies: Sequence[IRemapStrategy]


class IPathEvaluator(DPathEvaluator, metaclass=MPathEvaluator):
    """Nominal interface for evaluating relative paths and pruning directories."""

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> DEvaluationResult:
        raise NotImplementedError

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        raise NotImplementedError
