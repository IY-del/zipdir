"""Concrete domain data models and value helpers for zipdir."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field


class RuleKind(Enum):
    """Classification of rule types in .zipignore, directly indexed by count of '!' marks."""

    EXCLUDE = 0
    RESCUE = 1
    REDELETE = 2


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
    match stripped:
        case s if s in CANONICAL_TARGETS:
            return CANONICAL_TARGETS[s]
        case s:
            return s.rstrip("/")


def redelete_matches_rescue(redelete_target: str, rescued_target: str | None) -> bool:
    """Check whether a REDELETE target cancels a given RESCUE target."""
    match rescued_target:
        case None:
            return True
        case str() as target:
            return normalize_target(redelete_target) == normalize_target(target)


def normalize_posix_path(path: PurePosixPath) -> PurePosixPath:
    """Resolve '.' and '..' segments within a relative PurePosixPath."""
    stack: list[str] = []
    for part in path.parts:
        match part:
            case "" | ".":
                continue
            case "..":
                if stack:
                    stack.pop()
            case _:
                stack.append(part)
    return PurePosixPath(*stack) if stack else PurePosixPath()


@dataclass(frozen=True)
class ParsedRule:
    """AST representation for an interpreted .zipignore rule."""

    kind: RuleKind
    target: str
    pattern: str

    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("ParsedRule invariant violated: pattern must be non-empty")
        if "?" in self.target:
            raise ValueError("ParsedRule invariant violated: '?' is prohibited in target")


@dataclass(frozen=True)
class IgnoreRule:
    """Compiled .zipignore rule with optional rescue / remapping target."""

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
class EvaluationResult:
    """Outcome of evaluating a path against a compiled rule set."""

    is_excluded: bool
    arc_path: PurePosixPath | None
    matched_rule: IgnoreRule | None

    def __post_init__(self) -> None:
        match (self.is_excluded, self.arc_path):
            case (True, PurePosixPath()):
                raise ValueError(
                    "EvaluationResult invariant violated: excluded path cannot have an arc_path"
                )
            case (False, None):
                raise ValueError(
                    "EvaluationResult invariant violated: included path must have an arc_path"
                )
            case _:
                pass

    def __iter__(self) -> Iterator[bool | PurePosixPath | IgnoreRule | None]:
        yield self.is_excluded
        yield self.arc_path
        yield self.matched_rule


@dataclass(frozen=True)
class ResolvedOutput:
    """Resolved archive output path and collision metadata."""

    path: Path
    explicit_zip: bool
    stem: str
    fell_back: bool = False

    def __post_init__(self) -> None:
        match (self.explicit_zip, self.fell_back):
            case (True, True):
                raise ValueError(
                    "ResolvedOutput invariant violated: explicit .zip path cannot fall back"
                )
            case _:
                pass


class ScopedRule(BaseModel):
    """Rule line paired with its directory scope (relative to packaging source)."""

    scope: PurePosixPath = Field(default_factory=PurePosixPath)
    rule: str


class PresetModel(BaseModel):
    """Pydantic schema for preset definitions."""

    name: str = ""
    description: str = ""
    rules: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    source_path: Path | None = None


class PackagerConfig(BaseModel):
    """Configuration options for directory packaging."""

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
