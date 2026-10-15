"""Minimal concrete path evaluator (base stage for progressive inheritance)."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.evaluator.strategies import (
    DEFAULT_REMAP_STRATEGIES,
    DEFAULT_RULE_TRANSITIONS,
    EvaluationState,
)
from zipdir.interfaces.evaluator import IPathEvaluator, IRemapStrategy, IRuleTransition
from zipdir.interfaces.interpreter import IRuleInterpreter, MRuleInterpreter
from zipdir.interfaces.models import DIgnoreRule, DScopedRule, RuleKind
from zipdir.models import EvaluationResult, IgnoreRule


def _as_ignore_rule(rule: DIgnoreRule) -> IgnoreRule:
    if isinstance(rule, IgnoreRule):
        return rule
    return IgnoreRule(
        raw=rule.raw,
        kind=rule.kind,
        target=rule.target,
        pattern=rule.pattern,
        regex=rule.regex,
        is_dir_only=rule.is_dir_only,
        has_slash=rule.has_slash,
        scope=rule.scope,
    )


class PathEvaluator(IPathEvaluator):
    """Minimal concrete evaluator performing ancestor and target rule evaluation."""

    rules: tuple[IgnoreRule, ...]
    transitions: Mapping[RuleKind, IRuleTransition]
    remap_strategies: Sequence[IRemapStrategy]

    def __init__(
        self,
        rules: Sequence[DIgnoreRule | str | DScopedRule] = (),
        interpreter: IRuleInterpreter | None = None,
        transitions: Mapping[RuleKind, IRuleTransition] | None = None,
        remap_strategies: Sequence[IRemapStrategy] | None = None,
        create_interpreter: MRuleInterpreter = IRuleInterpreter,
    ) -> None:
        if all(isinstance(r, DIgnoreRule) for r in rules):
            self.rules = tuple(_as_ignore_rule(r) for r in rules if isinstance(r, DIgnoreRule))
        else:
            compiler = interpreter or create_interpreter()
            self.rules = tuple(_as_ignore_rule(r) for r in compiler.compile_all(rules))
        self.transitions = transitions if transitions is not None else DEFAULT_RULE_TRANSITIONS
        self.remap_strategies = (
            remap_strategies if remap_strategies is not None else DEFAULT_REMAP_STRATEGIES
        )

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> EvaluationResult:
        """Evaluate path against rules, returning EvaluationResult(is_excluded, arc_path, matched_rule)."""
        state = self._evaluate_ancestors(rel_path.parts)
        self._evaluate_target(rel_path, is_dir, state)

        if state.is_excluded:
            excluded_rule = (
                _as_ignore_rule(state.excluded_by) if state.excluded_by is not None else None
            )
            return EvaluationResult(True, None, excluded_rule)
        if state.rescued_by is None:
            return EvaluationResult(False, rel_path, None)

        rescued_rule = _as_ignore_rule(state.rescued_by)
        arc_rel = self._resolve_rescued_path(
            rel_path, rescued_rule, state.shallowest_excluded_ancestor
        )
        return EvaluationResult(False, arc_rel, rescued_rule)

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        """Minimal base pruning behavior (overridden in pruning.py)."""
        return False

    def _resolve_rescued_path(
        self,
        rel_path: PurePosixPath,
        rescued_by: IgnoreRule,
        shallowest_excluded_ancestor: PurePosixPath | None,
    ) -> PurePosixPath:
        """Base hook returning original relative path (extended in remapped.py)."""
        return rel_path

    def _evaluate_ancestors(self, parts: tuple[str, ...]) -> EvaluationState:
        state = EvaluationState()
        for k in range(1, len(parts)):
            anc = PurePosixPath(*parts[:k])
            anc_str = anc.as_posix()
            for r in self.rules:
                match_str = self._scoped_target(anc, anc_str, r.scope)
                if match_str is not None and r.regex.search(match_str):
                    self.transitions[r.kind].apply(state, r, ancestor=anc)
        return state

    def _evaluate_target(
        self, rel_path: PurePosixPath, is_dir: bool, state: EvaluationState
    ) -> None:
        posix_str = rel_path.as_posix()
        for r in self.rules:
            if r.is_dir_only and not is_dir:
                continue
            target_str = self._scoped_target(rel_path, posix_str, r.scope)
            if target_str is not None and r.regex.search(target_str):
                self.transitions[r.kind].apply(state, r)

    def _scoped_target(
        self, path: PurePosixPath, posix_str: str, scope: PurePosixPath
    ) -> str | None:
        if scope == PurePosixPath():
            return posix_str
        if not path.is_relative_to(scope) or path == scope:
            return None
        return path.relative_to(scope).as_posix()
