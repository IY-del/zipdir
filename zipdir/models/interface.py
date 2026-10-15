"""Data contracts (D*), RuleKind enum, and MInterface base metaclass for zipdir."""

import re
from collections.abc import Iterator, Sequence
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
