"""Concrete data models and pure domain value helpers implementing D* contracts."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

from zipdir.interfaces import (
    DEvaluationResult,
    DEvaluationState,
    DIgnoreRule,
    DPackagerConfig,
    DParsedRule,
    DPreset,
    DRemapContext,
    DResolvedOutput,
    DScopedRule,
    DSqueezeBuffer,
    RuleKind,
)

CANONICAL_TARGETS: dict[str, str] = {
    "": "",
    ".": "./",
    "./": "./",
    "..": "../",
    "../": "../",
    "/": "/",
}


def normalize_target(target: str) -> str:
    """Normalize a rescue/redelete destination target into canonical form."""
    stripped = target.strip()
    if stripped in CANONICAL_TARGETS:
        return CANONICAL_TARGETS[stripped]
    return stripped.rstrip("/")


def redelete_matches_rescue(redelete_target: str, rescued_target: str | None) -> bool:
    """Check whether a REDELETE target cancels a given RESCUE target."""
    if rescued_target is None:
        return True
    return normalize_target(redelete_target) == normalize_target(rescued_target)


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


@dataclass(frozen=True)
class ParsedRule(DParsedRule):
    """Concrete AST representation for an interpreted .zipignore rule."""

    kind: RuleKind
    target: str
    pattern: str

    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("ParsedRule invariant violated: pattern must be non-empty")
        if "?" in self.target:
            raise ValueError("ParsedRule invariant violated: '?' is prohibited in target")


@dataclass(frozen=True)
class IgnoreRule(DIgnoreRule):
    """Concrete compiled .zipignore rule with optional rescue / remapping target."""

    raw: str
    kind: RuleKind
    target: str
    pattern: str
    regex: re.Pattern[str]
    is_dir_only: bool
    has_slash: bool
    scope: PurePosixPath = PurePosixPath()

    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("IgnoreRule invariant violated: pattern must be non-empty")
        if "?" in self.target:
            raise ValueError("IgnoreRule invariant violated: '?' is prohibited in target")
        if self.scope.is_absolute():
            raise ValueError("IgnoreRule invariant violated: scope must be a relative path")


@dataclass(frozen=True)
class EvaluationResult(DEvaluationResult):
    """Concrete outcome of evaluating a path against a compiled rule set."""

    is_excluded: bool
    arc_path: PurePosixPath | None
    matched_rule: IgnoreRule | None

    def __post_init__(self) -> None:
        if self.is_excluded and self.arc_path is not None:
            raise ValueError(
                "EvaluationResult invariant violated: excluded path cannot have an arc_path"
            )
        if not self.is_excluded and self.arc_path is None:
            raise ValueError(
                "EvaluationResult invariant violated: included path must have an arc_path"
            )

    def __iter__(self) -> Iterator[bool | PurePosixPath | IgnoreRule | None]:
        yield self.is_excluded
        yield self.arc_path
        yield self.matched_rule


@dataclass(frozen=True)
class ResolvedOutput(DResolvedOutput):
    """Concrete resolved archive output path and collision metadata."""

    path: Path
    explicit_zip: bool
    stem: str
    fell_back: bool = False

    def __post_init__(self) -> None:
        if self.explicit_zip and self.fell_back:
            raise ValueError(
                "ResolvedOutput invariant violated: explicit .zip path cannot fall back"
            )


class ScopedRule(BaseModel, DScopedRule):
    """Concrete rule line paired with its directory scope (relative to packaging source)."""

    scope: PurePosixPath = Field(default_factory=PurePosixPath)
    rule: str


class PresetModel(BaseModel, DPreset):
    """Concrete Pydantic schema for preset definitions."""

    name: str = ""
    description: str = ""
    rules: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    source_path: Path | None = None


class PackagerConfig(BaseModel, DPackagerConfig):
    """Concrete configuration options for directory packaging."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Path
    output: Path
    name: str = Field(min_length=1)
    preset_name: str
    rules: list[str | ScopedRule | IgnoreRule] = Field(default_factory=list)
    compression: int = Field(default=6, ge=0, le=9)
    flat: bool = False
    dry_run: bool = False
    force: bool = False
    verbose: bool = False


class SqueezeBuffer[T](DSqueezeBuffer[T]):
    """Concrete mutable buffer state for compile-time rule squeezing."""

    items: list[T]
    parsed_meta: list[DParsedRule]
    seen: dict[tuple[PurePosixPath, str], list[int]]

    def __init__(self) -> None:
        self.items = []
        self.parsed_meta = []
        self.seen = {}

    def shift_indices(self, removed_idx: int) -> None:
        """Adjust recorded index positions after an element removal."""
        for key, idx_list in self.seen.items():
            self.seen[key] = [i - 1 if i > removed_idx else i for i in idx_list if i != removed_idx]


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
