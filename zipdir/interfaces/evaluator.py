"""Interfaces for path evaluation against ignore rules and destination remapping."""

from collections.abc import Mapping
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from zipdir.interfaces.glob import IGlobCompiler
from zipdir.models import EvaluationResult, IgnoreRule, RuleKind


class RemapContext(BaseModel):
    """Context holding evaluation parameters for path remapping."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    rel_path: PurePosixPath
    rule: IgnoreRule
    target: str

    def __init__(
        self,
        rel_path: PurePosixPath | None = None,
        rule: IgnoreRule | None = None,
        target: str = "",
        **data: object,
    ) -> None:
        if rel_path is not None:
            data.setdefault("rel_path", rel_path)
        if rule is not None:
            data.setdefault("rule", rule)
        if target:
            data.setdefault("target", target)
        super().__init__(**data)


class IRuleTransition:
    """Strategy interface for state transitions triggered by matched rules."""

    def transition(
        self,
        current_excluded: bool,
        current_arc: PurePosixPath | None,
        rule: IgnoreRule,
        remap_fn: object,
        rel_path: PurePosixPath,
    ) -> tuple[bool, PurePosixPath | None]:
        raise NotImplementedError


class IRemapStrategy:
    """Strategy interface for destination target path remapping."""

    def remap(self, context: RemapContext) -> PurePosixPath | None:
        raise NotImplementedError


class IPathEvaluator:
    """Interface for evaluating filesystem paths against ignore rules."""

    glob_compiler: IGlobCompiler
    rules: tuple[IgnoreRule, ...]
    transitions: Mapping[RuleKind, IRuleTransition]
    remap_strategies: Mapping[str, IRemapStrategy]

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> EvaluationResult:
        raise NotImplementedError

    def is_directory_pruned(self, dir_rel_path: PurePosixPath) -> bool:
        raise NotImplementedError

    def remap(self, rel_path: PurePosixPath, rule: IgnoreRule) -> PurePosixPath | None:
        raise NotImplementedError
