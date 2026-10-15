"""Interfaces for path evaluation against ignore rules and destination remapping."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

from zipdir.interfaces.glob import IGlobCompiler
from zipdir.models import EvaluationResult, IgnoreRule, RuleKind


@dataclass(frozen=True)
class RemapContext:
    """Context holding evaluation parameters for path remapping."""

    rel_path: PurePosixPath
    rule: IgnoreRule
    target: str


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
