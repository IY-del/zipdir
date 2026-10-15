"""Concrete rule transition and 3-tier coordinate remapping strategies."""

from dataclasses import dataclass
from pathlib import PurePosixPath

from zipdir.interfaces.evaluator import (
    DEvaluationState,
    DRemapContext,
    IRemapStrategy,
    IRuleTransition,
)
from zipdir.interfaces.models import DIgnoreRule, RuleKind
from zipdir.models import (
    IgnoreRule,
    normalize_posix_path,
    redelete_matches_rescue,
)


@dataclass
class EvaluationState(DEvaluationState):
    """Concrete mutable state tracking exclusion, rescue, and shallowest excluded ancestor."""

    is_excluded: bool = False
    shallowest_excluded_ancestor: PurePosixPath | None = None
    excluded_by: IgnoreRule | None = None
    rescued_by: IgnoreRule | None = None


@dataclass(frozen=True)
class RemapContext(DRemapContext):
    """Concrete coordinate parameters passed to IRemapStrategy implementations."""

    rel_path: PurePosixPath
    rescued_by: IgnoreRule
    shallowest_excluded_ancestor: PurePosixPath | None
    sub_path: PurePosixPath
    anchor_parent: PurePosixPath


class ExcludeTransition(IRuleTransition):
    """Concrete transition for EXCLUDE rules: marks state excluded and records shallowest ancestor."""

    def apply(
        self,
        state: DEvaluationState,
        rule: DIgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        state.is_excluded = True
        state.excluded_by = rule
        state.rescued_by = None
        if ancestor is not None and state.shallowest_excluded_ancestor is None:
            state.shallowest_excluded_ancestor = ancestor


class RescueTransition(IRuleTransition):
    """Concrete transition for RESCUE rules: marks state included and records active rescue rule."""

    def apply(
        self,
        state: DEvaluationState,
        rule: DIgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        state.is_excluded = False
        state.rescued_by = rule
        state.excluded_by = None


class RedeleteTransition(IRuleTransition):
    """Concrete transition for REDELETE rules: cancels prior rescue when destination target matches."""

    def apply(
        self,
        state: DEvaluationState,
        rule: DIgnoreRule,
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


def _combine_dest(dest_dir: PurePosixPath, sub_path: PurePosixPath) -> PurePosixPath:
    clean_dir = PurePosixPath() if dest_dir == PurePosixPath(".") else dest_dir
    return clean_dir / sub_path if clean_dir != PurePosixPath() else sub_path


class PreserveHierarchyRemapStrategy(IRemapStrategy):
    """Concrete Strategy for '.' or './': preserves original relative path from archive root."""

    def matches(self, target: str) -> bool:
        return target in (".", "./")

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
        return ctx.rel_path


class ArchiveRootRemapStrategy(IRemapStrategy):
    """Concrete Strategy for '/...': places rescued item relative to the archive root."""

    def matches(self, target: str) -> bool:
        return target.startswith("/")

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
        dest_dir = normalize_posix_path(PurePosixPath(ctx.rescued_by.target.lstrip("/")))
        return _combine_dest(dest_dir, ctx.sub_path)


class LocalScopeRemapStrategy(IRemapStrategy):
    """Concrete Strategy for './{to}': places rescued item relative to local scope or ancestor."""

    def matches(self, target: str) -> bool:
        return target.startswith("./") and target not in (".", "./")

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
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
        return _combine_dest(normalize_posix_path(raw_dest), ctx.sub_path)


class ParentClimbRemapStrategy(IRemapStrategy):
    """Concrete Strategy for '..' or '../...': climbs N parent levels from anchor_parent."""

    def matches(self, target: str) -> bool:
        return target in ("..", "../") or target.startswith("../")

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
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
        return _combine_dest(normalize_posix_path(combined), ctx.sub_path)


class ExileRemapStrategy(IRemapStrategy):
    """Concrete fallback Strategy (omitted prefix '!' or '{to}!'): exiles to excluded parent."""

    def matches(self, target: str) -> bool:
        return True

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
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
        return _combine_dest(normalize_posix_path(raw_dest), ctx.sub_path)


DEFAULT_REMAP_STRATEGIES: tuple[IRemapStrategy, ...] = (
    PreserveHierarchyRemapStrategy(),
    ArchiveRootRemapStrategy(),
    LocalScopeRemapStrategy(),
    ParentClimbRemapStrategy(),
    ExileRemapStrategy(),
)
