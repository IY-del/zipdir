"""Data models and schemas for zipdir packaging and ignore rules."""

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


@dataclass(frozen=True)
class ParsedRule:
    """Intermediary AST representation for an interpreted .zipignore rule."""

    kind: RuleKind
    target: str
    pattern: str


@dataclass(frozen=True)
class IgnoreRule:
    """Represents a compiled .zipignore pattern with optional rescue / remapping target."""

    raw: str
    kind: RuleKind
    target: str
    pattern: str
    regex: re.Pattern[str]
    is_dir_only: bool
    has_slash: bool
    scope: PurePosixPath = PurePosixPath()


@dataclass(frozen=True)
class EvaluationResult:
    """Outcome of evaluating a path against a compiled rule set.

    Supports both named attribute access and 3-tuple unpacking:
    `is_excluded, arc_path, matched_rule = evaluator.evaluate(path, is_dir)`
    """

    is_excluded: bool
    arc_path: PurePosixPath | None
    matched_rule: IgnoreRule | None

    def __iter__(self) -> Iterator[bool | PurePosixPath | IgnoreRule | None]:
        yield self.is_excluded
        yield self.arc_path
        yield self.matched_rule


class ScopedRule(BaseModel):
    """A rule line paired with its directory scope (relative to packaging source)."""

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
    name: str
    preset_name: str
    rules: list[str | ScopedRule | IgnoreRule] = Field(default_factory=list)
    compression: int = 6
    flat: bool = False
    dry_run: bool = False
    force: bool = False
    verbose: bool = False
