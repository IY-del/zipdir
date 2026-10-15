"""Squeezed rule interpreter via progressive inheritance over base.RuleInterpreter."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.glob import IGlobCompiler
from zipdir.interfaces.interpreter import IRuleSqueezer, ISqueezeStrategy
from zipdir.interpreter.base import RuleInterpreter as BaseRuleInterpreter
from zipdir.interpreter.strategies import DEFAULT_SQUEEZE_STRATEGIES, SqueezeBuffer
from zipdir.models import IgnoreRule, ParsedRule, RuleKind, ScopedRule

type _StagedCompileEntry = tuple[str, ParsedRule, PurePosixPath] | IgnoreRule


class RuleInterpreter(BaseRuleInterpreter, IRuleSqueezer):
    """Extends base RuleInterpreter with target-aware compile-time phagocytosis (rule squeezing)."""

    squeeze_strategies: Mapping[RuleKind, ISqueezeStrategy]

    def __init__(
        self,
        glob_compiler: IGlobCompiler | None = None,
        squeeze_strategies: Mapping[RuleKind, ISqueezeStrategy] | None = None,
    ) -> None:
        super().__init__(glob_compiler=glob_compiler)
        self.squeeze_strategies = (
            squeeze_strategies if squeeze_strategies is not None else DEFAULT_SQUEEZE_STRATEGIES
        )

    def squeeze(self, rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
        """Squeeze rule lines by pattern and scope with target-aware phagocytosis."""
        normalized = [
            entry for item in rules if (entry := self._normalize_squeeze_item(item)) is not None
        ]
        return self._squeeze_staged(normalized)

    def compile_all(
        self, rules: Sequence[str | ScopedRule | IgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects."""
        if not squeeze:
            return super().compile_all(rules)

        normalized = [
            entry for item in rules if (entry := self._normalize_compile_item(item)) is not None
        ]
        staged = self._squeeze_staged(normalized)
        compiled: list[IgnoreRule] = []
        for entry in staged:
            match entry:
                case IgnoreRule() as ir:
                    compiled.append(ir)
                case (str() as raw, ParsedRule() as parsed, PurePosixPath() as scope):
                    compiled.append(self._build_rule(raw, parsed, scope))
        return tuple(compiled)

    def _normalize_squeeze_item(
        self, item: str | ScopedRule
    ) -> tuple[PurePosixPath, ParsedRule, str | ScopedRule] | None:
        match item:
            case ScopedRule(scope=scope, rule=line):
                out_item = item
            case str() as line:
                scope = PurePosixPath()
                out_item = line
            case _:
                return None

        match self.parse_components(line):
            case None:
                return None
            case ParsedRule() as parsed:
                return scope, parsed, out_item

    def _normalize_compile_item(
        self, item: str | ScopedRule | IgnoreRule
    ) -> tuple[PurePosixPath, ParsedRule, _StagedCompileEntry] | None:
        match item:
            case IgnoreRule() as ir:
                return (
                    ir.scope,
                    ParsedRule(ir.kind, ir.target, ir.pattern),
                    ir,
                )
            case ScopedRule(scope=scope, rule=line):
                pass
            case str() as line:
                scope = PurePosixPath()
            case _:
                return None

        match self.parse_components(line):
            case None:
                return None
            case ParsedRule() as parsed:
                return scope, parsed, (line, parsed, scope)

    def _squeeze_staged[T](self, entries: Sequence[tuple[PurePosixPath, ParsedRule, T]]) -> list[T]:
        """Template skeleton that squeezes normalized rule entries using RuleKind strategies."""
        buffer: SqueezeBuffer[T] = SqueezeBuffer()
        for scope, parsed, payload in entries:
            key = (scope, parsed.pattern)
            match buffer.seen.get(key):
                case None | []:
                    buffer.seen[key] = [len(buffer.items)]
                    buffer.items.append(payload)
                    buffer.parsed_meta.append(parsed)
                case list() as indices:
                    self.squeeze_strategies[parsed.kind].apply(
                        buffer, key, indices, parsed, payload
                    )
        return buffer.items
