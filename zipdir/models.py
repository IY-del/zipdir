"""Data models, class invariants (D*), and nominal interfaces (I*) for zipdir."""

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field


class RuleKind(Enum):
    """Classification of rule types in .zipignore, directly indexed by count of '!' marks."""

    EXCLUDE = 0
    RESCUE = 1
    REDELETE = 2


# ==============================================================================
# Data Contracts & Class Invariants (D*)
# ==============================================================================
class DParsedRule:
    """Data contract and invariant for an interpreted .zipignore AST node.

    Invariants:
    - `pattern` is a non-empty string (`len(pattern) > 0`).
    - `target` never contains legacy `'?'` prefix characters (`'?' not in target`).
    """

    kind: RuleKind
    target: str
    pattern: str


@dataclass(frozen=True)
class ParsedRule(DParsedRule):
    """Intermediary AST representation for an interpreted .zipignore rule."""

    kind: RuleKind
    target: str
    pattern: str

    def __post_init__(self) -> None:
        if not self.pattern:
            raise ValueError("ParsedRule invariant violated: pattern must be non-empty")
        if "?" in self.target:
            raise ValueError("ParsedRule invariant violated: '?' is prohibited in target")


class DIgnoreRule(DParsedRule):
    """Data contract and invariant for a compiled .zipignore rule.

    Invariants:
    - Preserves `DParsedRule` invariants (`pattern != ""`, `'?' not in target`).
    - `scope` is a relative `PurePosixPath` (`not scope.is_absolute()`).
    """

    raw: str
    regex: re.Pattern[str]
    is_dir_only: bool
    has_slash: bool
    scope: PurePosixPath


@dataclass(frozen=True)
class IgnoreRule(DIgnoreRule):
    """Represents a compiled .zipignore pattern with optional rescue / remapping target."""

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


class DEvaluationResult:
    """Data contract and invariant for path evaluation outcomes.

    Invariants:
    - `(is_excluded is True and arc_path is None)` or
      `(is_excluded is False and arc_path is not None)`.
    """

    is_excluded: bool
    arc_path: PurePosixPath | None
    matched_rule: IgnoreRule | None


@dataclass(frozen=True)
class EvaluationResult(DEvaluationResult):
    """Outcome of evaluating a path against a compiled rule set.

    Supports both named attribute access and 3-tuple unpacking:
    `is_excluded, arc_path, matched_rule = evaluator.evaluate(path, is_dir)`
    """

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


class DResolvedOutput:
    """Data contract and invariant for resolved archive output paths.

    Invariants:
    - `explicit_zip is True` implies `fell_back is False`.
    - `stem` is a non-empty archive stem string.
    """

    path: Path
    explicit_zip: bool
    stem: str
    fell_back: bool


@dataclass(frozen=True)
class ResolvedOutput(DResolvedOutput):
    """Resolved archive output path and collision metadata."""

    path: Path
    explicit_zip: bool
    stem: str
    fell_back: bool = False

    def __post_init__(self) -> None:
        if self.explicit_zip and self.fell_back:
            raise ValueError(
                "ResolvedOutput invariant violated: explicit .zip path cannot fall back"
            )


class DScopedRule:
    """Data contract and invariant for a directory-scoped rule line."""

    scope: PurePosixPath
    rule: str


class ScopedRule(BaseModel, DScopedRule):
    """A rule line paired with its directory scope (relative to packaging source)."""

    scope: PurePosixPath = Field(default_factory=PurePosixPath)
    rule: str


class DPreset:
    """Data contract and invariant for preset definitions."""

    name: str
    description: str
    rules: list[str]
    extends: list[str]
    source_path: Path | None


class PresetModel(BaseModel, DPreset):
    """Pydantic schema for preset definitions."""

    name: str = ""
    description: str = ""
    rules: list[str] = Field(default_factory=list)
    extends: list[str] = Field(default_factory=list)
    source_path: Path | None = None


class DPackagerConfig:
    """Data contract and invariant for directory packaging configuration.

    Invariants:
    - `compression` is within `0..9`.
    - `name` is a non-empty single directory name.
    """

    source: Path
    output: Path
    name: str
    preset_name: str
    rules: list[str | ScopedRule | IgnoreRule]
    compression: int
    flat: bool
    dry_run: bool
    force: bool
    verbose: bool


class PackagerConfig(BaseModel, DPackagerConfig):
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


# ==============================================================================
# Horizontally Separated Behavioral Interfaces (I* / D*) — DIP & ISP
# ==============================================================================
class DGlobCompiler:
    """State invariant for gitignore glob compilers."""

    token_pattern: re.Pattern[str]


class IGlobCompiler(DGlobCompiler):
    """Nominal interface for compiling gitignore-style glob patterns into regular expressions."""

    def interpret(self, pattern: str) -> tuple[re.Pattern[str], bool, bool]:
        raise NotImplementedError


class DRuleInterpreter:
    """State invariant for 4-component .zipignore rule interpreters."""

    glob_compiler: IGlobCompiler


class IRuleInterpreter(DRuleInterpreter):
    """Nominal interface for parsing and compiling .zipignore rules."""

    def parse_components(self, line: str) -> ParsedRule | None:
        raise NotImplementedError

    def interpret(self, line: str, scope: PurePosixPath = PurePosixPath()) -> IgnoreRule | None:
        raise NotImplementedError

    def compile_all(
        self, rules: Sequence[str | ScopedRule | IgnoreRule]
    ) -> tuple[IgnoreRule, ...]:
        raise NotImplementedError


class IRuleSqueezer(IRuleInterpreter):
    """Extended nominal interface supporting target-aware compile-time rule squeezing."""

    def squeeze(self, rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
        raise NotImplementedError


class DPathEvaluator:
    """State invariant for runtime path evaluators."""

    rules: tuple[IgnoreRule, ...]


class IPathEvaluator(DPathEvaluator):
    """Nominal interface for evaluating relative paths and pruning directories."""

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> EvaluationResult:
        raise NotImplementedError

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        raise NotImplementedError


class DOutputResolver:
    """State invariant for output path resolvers."""

    cwd: Path
    timestamp_fn: Callable[[], str]


class IOutputResolver(DOutputResolver):
    """Nominal interface for 3-tier output path resolution and collision fallback."""

    def normalize_cli_args(self, args: Sequence[str]) -> list[str]:
        raise NotImplementedError

    def resolve_with_metadata(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> ResolvedOutput:
        raise NotImplementedError

    def resolve(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> Path:
        raise NotImplementedError


class DPresetCatalog:
    """State invariant for preset discovery and C3 cascade resolution."""

    preset_dirs: list[Path]
    interpreter: IRuleSqueezer


class IPresetCatalog(DPresetCatalog):
    """Nominal interface for preset loading, C3 linearization, and 4-tier cascading."""

    def parse_file(self, file: Path) -> PresetModel:
        raise NotImplementedError

    def load_all(self) -> dict[str, PresetModel]:
        raise NotImplementedError

    def linearize_presets(
        self,
        name: str,
        raw_presets: Mapping[str, PresetModel],
    ) -> list[str]:
        raise NotImplementedError

    def discover_sub_zipignores(self, source: Path) -> list[tuple[PurePosixPath, Path]]:
        raise NotImplementedError

    def resolve_cascade(
        self,
        source: Path,
        presets: dict[str, PresetModel] | None = None,
        *,
        preset: str | None = None,
        cli_rules: Sequence[str] = (),
        no_default_rules: bool = False,
    ) -> tuple[str, list[str | ScopedRule]]:
        raise NotImplementedError


class DReporter:
    """State invariant for terminal/UI reporters."""

    use_color: bool


class IReporter(DReporter):
    """Nominal interface for reporting preset listings, dry-run previews, and summaries."""

    def print_presets(self, presets: Mapping[str, PresetModel]) -> None:
        raise NotImplementedError

    def print_dry_run(
        self,
        config: PackagerConfig,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError

    def print_summary(
        self,
        config: PackagerConfig,
        output: Path,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError


class DPackager:
    """State invariant for archive packagers."""

    config: PackagerConfig
    evaluator: IPathEvaluator
    reporter: IReporter
    compiled_rules: list[IgnoreRule]
    rescued_files: list[tuple[str, str]]
    excluded_files: list[str]


class IPackager(DPackager):
    """Nominal interface for traversing sources and producing ZIP archives."""

    def collect_members(self) -> Iterator[tuple[Path, str]]:
        raise NotImplementedError

    def write_archive(self, path: Path, entries: Sequence[tuple[Path, str]]) -> None:
        raise NotImplementedError

    def package(self) -> Path:
        raise NotImplementedError
