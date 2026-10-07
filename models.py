"""Data models and schemas for zipdir packaging and ignore rules."""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field


class RuleKind(Enum):
    """Classification of rule types in .zipignore, directly indexed by count of '!' marks."""

    EXCLUDE = 0
    RESCUE = 1
    REDELETE = 2


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
class ParsedRule:
    """Intermediary AST representation for an interpreted .zipignore rule."""

    kind: RuleKind
    target: str
    pattern: str


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

    source: Path
    output: Path
    name: str
    preset_name: str
    rules: list[str | ScopedRule] = Field(default_factory=list)
    compression: int = 6
    flat: bool = False
    dry_run: bool = False
    force: bool = False
    verbose: bool = False
