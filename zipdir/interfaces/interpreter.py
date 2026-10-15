"""Interfaces and FactoryMethod metaclasses for .zipignore rule interpretation and squeezing."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.glob import IGlobCompiler
from zipdir.interfaces.models import (
    DIgnoreRule,
    DParsedRule,
    DScopedRule,
    MInterface,
    RuleKind,
)


class DSqueezeBuffer[T]:
    """Mutable buffer state invariant for compile-time rule squeezing."""

    items: list[T]
    parsed_meta: list[DParsedRule]
    seen: dict[tuple[PurePosixPath, str], list[int]]

    def shift_indices(self, removed_idx: int) -> None:
        raise NotImplementedError


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
