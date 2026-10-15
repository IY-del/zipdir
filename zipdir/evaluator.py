"""Runtime path evaluation, smart remapping via Strategy/CoR, and non-greedy directory pruning."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from zipdir.interpreter import redelete_matches_rescue
from zipdir.models import (
    EvaluationResult,
    IgnoreRule,
    IPathEvaluator,
    IRuleInterpreter,
    RuleKind,
    ScopedRule,
)
from zipdir.squeezer import RuleInterpreter


def normalize_posix_path(path: PurePosixPath) -> PurePosixPath:
    """Resolve '.' and '..' segments within a relative PurePosixPath."""
    stack: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
        else:
            stack.append(part)
    return PurePosixPath(*stack) if stack else PurePosixPath()


# ==============================================================================
# 1. Rule Transition Strategies (State / Strategy for Hierarchical Phagocytosis)
# ==============================================================================
class DEvaluationState:
    """Mutable state invariant accumulated across ancestor and target evaluation."""

    is_excluded: bool
    shallowest_excluded_ancestor: PurePosixPath | None
    excluded_by: IgnoreRule | None
    rescued_by: IgnoreRule | None


@dataclass
class EvaluationState(DEvaluationState):
    """Tracks exclusion, rescue, and shallowest excluded ancestor across path evaluation."""

    is_excluded: bool = False
    shallowest_excluded_ancestor: PurePosixPath | None = None
    excluded_by: IgnoreRule | None = None
    rescued_by: IgnoreRule | None = None


class IRuleTransition:
    """Nominal Strategy interface for applying a matched IgnoreRule to EvaluationState."""

    def apply(
        self,
        state: EvaluationState,
        rule: IgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        raise NotImplementedError


class ExcludeTransition(IRuleTransition):
    """Transition for EXCLUDE rules: marks state excluded and records shallowest ancestor."""

    def apply(
        self,
        state: EvaluationState,
        rule: IgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        state.is_excluded = True
        state.excluded_by = rule
        state.rescued_by = None
        if ancestor is not None and state.shallowest_excluded_ancestor is None:
            state.shallowest_excluded_ancestor = ancestor


class RescueTransition(IRuleTransition):
    """Transition for RESCUE rules: marks state included and records active rescue rule."""

    def apply(
        self,
        state: EvaluationState,
        rule: IgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        state.is_excluded = False
        state.rescued_by = rule
        state.excluded_by = None


class RedeleteTransition(IRuleTransition):
    """Transition for REDELETE rules: cancels prior rescue only when destination target matches."""

    def apply(
        self,
        state: EvaluationState,
        rule: IgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        rescued_target = state.rescued_by.target if state.rescued_by is not None else None
        if state.rescued_by is None or redelete_matches_rescue(rule.target, rescued_target):
            state.is_excluded = True
            state.excluded_by = rule
            state.rescued_by = None


DEFAULT_RULE_TRANSITIONS: dict[RuleKind, IRuleTransition] = {
    RuleKind.EXCLUDE: ExcludeTransition(),
    RuleKind.RESCUE: RescueTransition(),
    RuleKind.REDELETE: RedeleteTransition(),
}


# ==============================================================================
# 2. 3-Tier Path Remapping Strategies (Strategy & Chain of Responsibility)
# ==============================================================================
class DRemapContext:
    """Data contract and invariant for path remapping context."""

    rel_path: PurePosixPath
    rescued_by: IgnoreRule
    shallowest_excluded_ancestor: PurePosixPath | None
    sub_path: PurePosixPath
    anchor_parent: PurePosixPath


@dataclass(frozen=True)
class RemapContext(DRemapContext):
    """Resolved coordinate parameters passed to IRemapStrategy implementations."""

    rel_path: PurePosixPath
    rescued_by: IgnoreRule
    shallowest_excluded_ancestor: PurePosixPath | None
    sub_path: PurePosixPath
    anchor_parent: PurePosixPath


class IRemapStrategy:
    """Nominal Strategy interface for resolving destination archive paths."""

    def matches(self, target: str) -> bool:
        raise NotImplementedError

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        raise NotImplementedError

    def _combine(self, dest_dir: PurePosixPath, sub_path: PurePosixPath) -> PurePosixPath:
        clean_dir = PurePosixPath() if dest_dir == PurePosixPath(".") else dest_dir
        return clean_dir / sub_path if clean_dir != PurePosixPath() else sub_path


class PreserveHierarchyRemapStrategy(IRemapStrategy):
    """Matches '.' or './': preserves original relative path from archive root."""

    def matches(self, target: str) -> bool:
        return target in (".", "./")

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        return ctx.rel_path


class ArchiveRootRemapStrategy(IRemapStrategy):
    """Matches '/...': places rescued item relative to the archive root."""

    def matches(self, target: str) -> bool:
        return target.startswith("/")

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        dest_dir = normalize_posix_path(PurePosixPath(ctx.rescued_by.target.lstrip("/")))
        return self._combine(dest_dir, ctx.sub_path)


class LocalScopeRemapStrategy(IRemapStrategy):
    """Matches './{to}': places rescued item relative to local scope or preserved ancestor."""

    def matches(self, target: str) -> bool:
        return target.startswith("./") and target not in (".", "./")

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        rel_sub = ctx.rescued_by.target.removeprefix("./").strip("/")
        scope = ctx.rescued_by.scope
        preserved_base = (
            scope
            if scope != PurePosixPath()
            else (
                ctx.shallowest_excluded_ancestor
                if ctx.shallowest_excluded_ancestor is not None
                else ctx.rel_path.parent
            )
        )
        raw_dest = preserved_base / rel_sub if rel_sub else preserved_base
        return self._combine(normalize_posix_path(raw_dest), ctx.sub_path)


class ParentClimbRemapStrategy(IRemapStrategy):
    """Matches '..' or '../...': climbs N parent levels from anchor_parent."""

    def matches(self, target: str) -> bool:
        return target in ("..", "../") or target.startswith("../")

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        current = (
            PurePosixPath() if ctx.anchor_parent == PurePosixPath(".") else ctx.anchor_parent
        )
        parts = [p for p in ctx.rescued_by.target.split("/") if p and p != "."]
        idx = 0
        while idx < len(parts) and parts[idx] == "..":
            current = (
                PurePosixPath()
                if current in (PurePosixPath(), PurePosixPath("."))
                else current.parent
            )
            idx += 1
        remainder = PurePosixPath(*parts[idx:]) if idx < len(parts) else PurePosixPath()
        combined = current / remainder if remainder != PurePosixPath() else current
        return self._combine(normalize_posix_path(combined), ctx.sub_path)


class ExileRemapStrategy(IRemapStrategy):
    """Default fallback strategy (omitted prefix '!' or '{to}!'): exiles to shallowest excluded parent."""

    def matches(self, target: str) -> bool:
        return True

    def remap(self, ctx: RemapContext) -> PurePosixPath:
        target = ctx.rescued_by.target
        has_ancestor = ctx.shallowest_excluded_ancestor is not None
        if not has_ancestor and not target and ctx.rel_path.parent == PurePosixPath("."):
            return ctx.rel_path

        exile_base = (
            ctx.anchor_parent
            if has_ancestor
            else (
                PurePosixPath()
                if ctx.rel_path.parent == PurePosixPath(".")
                else ctx.anchor_parent.parent
            )
        )
        raw_dest = exile_base / target if target else exile_base
        return self._combine(normalize_posix_path(raw_dest), ctx.sub_path)


DEFAULT_REMAP_STRATEGIES: tuple[IRemapStrategy, ...] = (
    PreserveHierarchyRemapStrategy(),
    ArchiveRootRemapStrategy(),
    LocalScopeRemapStrategy(),
    ParentClimbRemapStrategy(),
    ExileRemapStrategy(),
)


# ==============================================================================
# 3. Path Evaluator (Bridge with Rule Transitions & Remap Strategies)
# ==============================================================================
class PathEvaluator(IPathEvaluator):
    """Evaluates relative paths against compiled .zipignore rules with hierarchical phagocytosis."""

    rules: tuple[IgnoreRule, ...]
    transitions: Mapping[RuleKind, IRuleTransition]
    remap_strategies: Sequence[IRemapStrategy]

    def __init__(
        self,
        rules: Sequence[IgnoreRule | str | ScopedRule] = (),
        interpreter: IRuleInterpreter | None = None,
        transitions: Mapping[RuleKind, IRuleTransition] | None = None,
        remap_strategies: Sequence[IRemapStrategy] | None = None,
    ) -> None:
        if all(isinstance(r, IgnoreRule) for r in rules):
            self.rules = tuple(r for r in rules if isinstance(r, IgnoreRule))
        else:
            compiler = interpreter or RuleInterpreter()
            self.rules = compiler.compile_all(rules)
        self.transitions = transitions if transitions is not None else DEFAULT_RULE_TRANSITIONS
        self.remap_strategies = (
            remap_strategies if remap_strategies is not None else DEFAULT_REMAP_STRATEGIES
        )

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> EvaluationResult:
        """Evaluate path against rules, returning EvaluationResult(is_excluded, arc_path, matched_rule)."""
        state = self._evaluate_ancestors(rel_path.parts)
        self._evaluate_target(rel_path, is_dir, state)

        if state.is_excluded:
            return EvaluationResult(True, None, state.excluded_by)
        if state.rescued_by is None:
            return EvaluationResult(False, rel_path, None)

        arc_rel = self._remap_path(rel_path, state.rescued_by, state.shallowest_excluded_ancestor)
        return EvaluationResult(False, arc_rel, state.rescued_by)

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        """Check if an excluded directory has any active rescue rules that could target its contents."""
        if not self.evaluate(rel_dir, is_dir=True).is_excluded:
            return False

        posix_str = rel_dir.as_posix()
        for r in self.rules:
            if r.kind != RuleKind.RESCUE:
                continue
            if r.scope != PurePosixPath():
                if r.scope == rel_dir or r.scope.is_relative_to(rel_dir):
                    return False
                if not rel_dir.is_relative_to(r.scope):
                    continue
            clean_pat = r.pattern.lstrip("/")
            full_pat = (r.scope / clean_pat).as_posix() if r.scope != PurePosixPath() else clean_pat
            if full_pat.startswith(posix_str) or posix_str.startswith(full_pat.split("*")[0]):
                return False

        return True

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

    def _remap_path(
        self,
        rel_path: PurePosixPath,
        rescued_by: IgnoreRule,
        shallowest_excluded_ancestor: PurePosixPath | None,
    ) -> PurePosixPath:
        """Dispatch destination archive path calculation to the matching 3-tier IRemapStrategy."""
        sub_path = (
            rel_path.relative_to(shallowest_excluded_ancestor)
            if shallowest_excluded_ancestor is not None
            else PurePosixPath(rel_path.name)
        )
        anchor_parent = (
            shallowest_excluded_ancestor.parent
            if shallowest_excluded_ancestor is not None
            else rel_path.parent
        )
        ctx = RemapContext(
            rel_path=rel_path,
            rescued_by=rescued_by,
            shallowest_excluded_ancestor=shallowest_excluded_ancestor,
            sub_path=sub_path,
            anchor_parent=anchor_parent,
        )
        for strategy in self.remap_strategies:
            if strategy.matches(rescued_by.target):
                return strategy.remap(ctx)
        return rel_path

    def _scoped_target(
        self, path: PurePosixPath, posix_str: str, scope: PurePosixPath
    ) -> str | None:
        if scope == PurePosixPath():
            return posix_str
        if not path.is_relative_to(scope) or path == scope:
            return None
        return path.relative_to(scope).as_posix()


def evaluate_path(
    rel_path: PurePosixPath,
    is_dir: bool,
    rules: Sequence[IgnoreRule],
) -> tuple[bool, PurePosixPath | None, IgnoreRule | None]:
    """Evaluate path against rules, returning (is_excluded, arc_rel_path, matched_rule)."""
    res = PathEvaluator(rules).evaluate(rel_path, is_dir=is_dir)
    return res.is_excluded, res.arc_path, res.matched_rule
