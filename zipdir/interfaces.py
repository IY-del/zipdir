"""Pure abstract contracts: data invariants (D*), nominal interfaces (I*), and factories (M*).

This module defines the abstraction layer of zipdir without any concrete implementations
or dependencies on concrete modules, enforcing the Dependency Inversion Principle (DIP)
and Interface Segregation Principle (ISP).
"""

import re
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from enum import Enum
from pathlib import Path, PurePosixPath


class RuleKind(Enum):
    """Classification of rule types in .zipignore, directly indexed by count of '!' marks."""

    EXCLUDE = 0
    RESCUE = 1
    REDELETE = 2


class MInterface(type):
    """Base FactoryMethod metaclass supporting Constructor Strategy and DIP wiring."""

    _impl: type | None = None

    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, object]) -> None:
        super().__init__(name, bases, namespace)
        if not name.startswith(("I", "D")):
            for base in cls.__mro__[1:]:
                if isinstance(base, MInterface) and base.__name__.startswith("I"):
                    base._impl = cls

    def __call__(cls, *args: object, **kwargs: object) -> object:
        target = cls._impl if (cls.__name__.startswith("I") and cls._impl is not None) else cls
        return super(MInterface, target).__call__(*args, **kwargs)


# ==============================================================================
# 1. Data Contracts & Class Invariants (D*)
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


class DEvaluationResult:
    """Data contract and invariant for path evaluation outcomes.

    Invariants:
    - `(is_excluded is True and arc_path is None)` or
      `(is_excluded is False and arc_path is not None)`.
    """

    is_excluded: bool
    arc_path: PurePosixPath | None
    matched_rule: DIgnoreRule | None

    def __iter__(self) -> Iterator[bool | PurePosixPath | DIgnoreRule | None]:
        raise NotImplementedError


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


class DScopedRule:
    """Data contract and invariant for a directory-scoped rule line.

    Invariants:
    - `scope` is a relative `PurePosixPath` (`not scope.is_absolute()`).
    """

    scope: PurePosixPath
    rule: str


class DPreset:
    """Data contract and invariant for preset definitions."""

    name: str
    description: str
    rules: list[str]
    extends: list[str]
    source_path: Path | None


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
    rules: Sequence[str | DScopedRule | DIgnoreRule]
    compression: int
    flat: bool
    dry_run: bool
    force: bool
    verbose: bool


class DSqueezeBuffer[T]:
    """Mutable buffer state invariant for compile-time rule squeezing."""

    items: list[T]
    parsed_meta: list[DParsedRule]
    seen: dict[tuple[PurePosixPath, str], list[int]]

    def shift_indices(self, removed_idx: int) -> None:
        raise NotImplementedError


class DEvaluationState:
    """Mutable state invariant accumulated across ancestor and target path evaluation."""

    is_excluded: bool
    shallowest_excluded_ancestor: PurePosixPath | None
    excluded_by: DIgnoreRule | None
    rescued_by: DIgnoreRule | None


class DRemapContext:
    """Data contract and invariant for 3-tier path remapping context."""

    rel_path: PurePosixPath
    rescued_by: DIgnoreRule
    shallowest_excluded_ancestor: PurePosixPath | None
    sub_path: PurePosixPath
    anchor_parent: PurePosixPath


# ==============================================================================
# 2. Strategy Interfaces (I*)
# ==============================================================================
class ISqueezeStrategy:
    """Nominal Strategy interface for resolving rule collisions on identical (scope, pattern)."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: DParsedRule,
        entry: T,
    ) -> None:
        raise NotImplementedError


class IRuleTransition:
    """Nominal Strategy interface for applying a matched rule to DEvaluationState."""

    def apply(
        self,
        state: DEvaluationState,
        rule: DIgnoreRule,
        ancestor: PurePosixPath | None = None,
    ) -> None:
        raise NotImplementedError


class IRemapStrategy:
    """Nominal Strategy interface for resolving 3-tier destination archive paths."""

    def matches(self, target: str) -> bool:
        raise NotImplementedError

    def remap(self, ctx: DRemapContext) -> PurePosixPath:
        raise NotImplementedError


class IOutputTargetStrategy:
    """Nominal Strategy interface for classifying 3-tier raw output path prefixes."""

    def matches(self, raw: str) -> bool:
        raise NotImplementedError

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        raise NotImplementedError


class IArchiveEntryWriter:
    """Nominal Strategy interface for writing an entry into a ZipFile archive."""

    def matches(self, item: Path, source: Path) -> bool:
        raise NotImplementedError

    def write(self, archive: zipfile.ZipFile, item: Path, arcname: str) -> None:
        raise NotImplementedError


# ==============================================================================
# 3. Component State Contracts (D*), Interfaces (I*), and Factory Metaclasses (M*)
# ==============================================================================
class MGlobCompiler(MInterface):
    """FactoryMethod metaclass for IGlobCompiler."""

    def __call__(cls, *args: object, **kwargs: object) -> "IGlobCompiler":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DGlobCompiler:
    """State invariant for gitignore glob compilers."""

    token_pattern: re.Pattern[str]
    translators: Mapping[str, Callable[[str], str]]


class IGlobCompiler(DGlobCompiler, metaclass=MGlobCompiler):
    """Nominal interface for compiling gitignore-style glob patterns into regular expressions."""

    def interpret(self, pattern: str) -> tuple[re.Pattern[str], bool, bool]:
        raise NotImplementedError


class MRuleInterpreter(MInterface):
    """FactoryMethod metaclass for IRuleInterpreter."""

    def __call__(cls, *args: object, **kwargs: object) -> "IRuleInterpreter":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DRuleInterpreter:
    """State invariant for 4-component .zipignore rule interpreters."""

    glob_compiler: IGlobCompiler


class IRuleInterpreter(DRuleInterpreter, metaclass=MRuleInterpreter):
    """Nominal interface for parsing and compiling .zipignore rules."""

    def parse_components(self, line: str) -> DParsedRule | None:
        raise NotImplementedError

    def interpret(self, line: str, scope: PurePosixPath = PurePosixPath()) -> DIgnoreRule | None:
        raise NotImplementedError

    def compile_all(
        self, rules: Sequence[str | DScopedRule | DIgnoreRule]
    ) -> tuple[DIgnoreRule, ...]:
        raise NotImplementedError


class MRuleSqueezer(MRuleInterpreter):
    """FactoryMethod metaclass for IRuleSqueezer."""

    def __call__(cls, *args: object, **kwargs: object) -> "IRuleSqueezer":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DRuleSqueezer(DRuleInterpreter):
    """State invariant for target-aware rule squeezers."""

    squeeze_strategies: Mapping[RuleKind, ISqueezeStrategy]


class IRuleSqueezer(DRuleSqueezer, IRuleInterpreter, metaclass=MRuleSqueezer):
    """Extended nominal interface supporting target-aware compile-time rule squeezing."""

    def squeeze(self, rules: Sequence[str | DScopedRule]) -> list[str | DScopedRule]:
        raise NotImplementedError


class MPathEvaluator(MInterface):
    """FactoryMethod metaclass for IPathEvaluator."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPathEvaluator":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPathEvaluator:
    """State invariant for runtime path evaluators."""

    rules: tuple[DIgnoreRule, ...]
    transitions: Mapping[RuleKind, IRuleTransition]
    remap_strategies: Sequence[IRemapStrategy]


class IPathEvaluator(DPathEvaluator, metaclass=MPathEvaluator):
    """Nominal interface for evaluating relative paths and pruning directories."""

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> DEvaluationResult:
        raise NotImplementedError

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        raise NotImplementedError


class MOutputResolver(MInterface):
    """FactoryMethod metaclass for IOutputResolver."""

    def __call__(cls, *args: object, **kwargs: object) -> "IOutputResolver":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DOutputResolver:
    """State invariant for output path resolvers."""

    cwd: Path
    timestamp_fn: Callable[[], str]
    target_strategies: Sequence[IOutputTargetStrategy]


class IOutputResolver(DOutputResolver, metaclass=MOutputResolver):
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
    ) -> DResolvedOutput:
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


class MPresetCatalog(MInterface):
    """FactoryMethod metaclass for IPresetCatalog."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPresetCatalog":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPresetCatalog:
    """State invariant for preset discovery and C3 cascade resolution."""

    preset_dirs: list[Path]
    interpreter: IRuleSqueezer


class IPresetCatalog(DPresetCatalog, metaclass=MPresetCatalog):
    """Nominal interface for preset loading, C3 linearization, and 4-tier cascading."""

    def parse_file(self, file: Path) -> DPreset:
        raise NotImplementedError

    def load_all(self) -> dict[str, DPreset]:
        raise NotImplementedError

    def linearize_presets(
        self,
        name: str,
        raw_presets: Mapping[str, DPreset],
    ) -> list[str]:
        raise NotImplementedError

    def discover_sub_zipignores(self, source: Path) -> list[tuple[PurePosixPath, Path]]:
        raise NotImplementedError

    def resolve_cascade(
        self,
        source: Path,
        presets: Mapping[str, DPreset] | None = None,
        *,
        preset: str | None = None,
        cli_rules: Sequence[str] = (),
        no_default_rules: bool = False,
    ) -> tuple[str, list[str | DScopedRule]]:
        raise NotImplementedError


class MReporter(MInterface):
    """FactoryMethod metaclass for IReporter."""

    def __call__(cls, *args: object, **kwargs: object) -> "IReporter":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DReporter:
    """State invariant for terminal/UI reporters."""

    use_color: bool


class IReporter(DReporter, metaclass=MReporter):
    """Nominal interface for reporting preset listings, dry-run previews, and summaries."""

    def print_presets(self, presets: Mapping[str, DPreset]) -> None:
        raise NotImplementedError

    def print_dry_run(
        self,
        config: DPackagerConfig,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError

    def print_summary(
        self,
        config: DPackagerConfig,
        output: Path,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError


class MPackager(MInterface):
    """FactoryMethod metaclass for IPackager."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPackager":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPackager:
    """State invariant for archive packagers."""

    config: DPackagerConfig
    evaluator: IPathEvaluator
    reporter: IReporter
    entry_writers: Sequence[IArchiveEntryWriter]
    compiled_rules: list[DIgnoreRule]
    rescued_files: list[tuple[str, str]]
    excluded_files: list[str]


class IPackager(DPackager, metaclass=MPackager):
    """Nominal interface for traversing sources and producing ZIP archives."""

    def collect_members(self) -> Iterator[tuple[Path, str]]:
        raise NotImplementedError

    def write_archive(self, path: Path, entries: Sequence[tuple[Path, str]]) -> None:
        raise NotImplementedError

    def package(self) -> Path:
        raise NotImplementedError
