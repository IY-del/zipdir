"""Squeezed rule interpreter via progressive inheritance over base.RuleInterpreter."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.glob.interface import IGlobCompiler, MGlobCompiler
from zipdir.interpreter.base import RuleInterpreter as BaseRuleInterpreter
from zipdir.interpreter.interface import IRuleSqueezer, ISqueezeStrategy
from zipdir.interpreter.strategies import DEFAULT_SQUEEZE_STRATEGIES, SqueezeBuffer
from zipdir.models import (
    DIgnoreRule,
    DParsedRule,
    DScopedRule,
    IgnoreRule,
    ParsedRule,
    RuleKind,
    ScopedRule,
)


class RuleInterpreter(BaseRuleInterpreter, IRuleSqueezer):
    """Extends base RuleInterpreter with target-aware compile-time phagocytosis (rule squeezing)."""

    squeeze_strategies: Mapping[RuleKind, ISqueezeStrategy]

    def __init__(
        self,
        glob_compiler: IGlobCompiler | None = None,
        squeeze_strategies: Mapping[RuleKind, ISqueezeStrategy] | None = None,
        create_glob: MGlobCompiler = IGlobCompiler,
    ) -> None:
        super().__init__(glob_compiler=glob_compiler, create_glob=create_glob)
        self.squeeze_strategies = (
            squeeze_strategies if squeeze_strategies is not None else DEFAULT_SQUEEZE_STRATEGIES
        )

    def squeeze(self, rules: Sequence[str | DScopedRule]) -> list[str | ScopedRule]:
        """Squeeze rule lines by pattern and scope with target-aware phagocytosis."""
        normalized: list[tuple[PurePosixPath, DParsedRule, str | ScopedRule]] = []
        for item in rules:
            scope = item.scope if isinstance(item, DScopedRule) else PurePosixPath()
            line = item.rule if isinstance(item, DScopedRule) else item
            out_item: str | ScopedRule = (
                item
                if isinstance(item, (str, ScopedRule))
                else ScopedRule(scope=item.scope, rule=item.rule)
            )
            parsed = self.parse_components(line)
            if parsed is not None:
                normalized.append((scope, parsed, out_item))
        return self._squeeze_staged(normalized)

    def compile_all(
        self, rules: Sequence[str | DScopedRule | DIgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects."""
        if not squeeze:
            return super().compile_all(rules)

        type StagedEntry = tuple[str, DParsedRule, PurePosixPath] | IgnoreRule
        normalized: list[tuple[PurePosixPath, DParsedRule, StagedEntry]] = []
        for item in rules:
            if isinstance(item, IgnoreRule):
                parsed = ParsedRule(item.kind, item.target, item.pattern)
                normalized.append((item.scope, parsed, item))
            elif isinstance(item, DIgnoreRule):
                concrete_rule = IgnoreRule(
                    raw=item.raw,
                    kind=item.kind,
                    target=item.target,
                    pattern=item.pattern,
                    regex=item.regex,
                    is_dir_only=item.is_dir_only,
                    has_slash=item.has_slash,
                    scope=item.scope,
                )
                parsed = ParsedRule(item.kind, item.target, item.pattern)
                normalized.append((item.scope, parsed, concrete_rule))
            else:
                scope = item.scope if isinstance(item, DScopedRule) else PurePosixPath()
                line = item.rule if isinstance(item, DScopedRule) else item
                parsed_opt = self.parse_components(line)
                if parsed_opt is not None:
                    normalized.append((scope, parsed_opt, (line, parsed_opt, scope)))

        staged = self._squeeze_staged(normalized)
        return tuple(
            entry if isinstance(entry, IgnoreRule) else self._build_rule(*entry) for entry in staged
        )

    def _squeeze_staged[T](
        self, entries: Sequence[tuple[PurePosixPath, DParsedRule, T]]
    ) -> list[T]:
        """Template skeleton that squeezes normalized rule entries using RuleKind strategies."""
        buffer: SqueezeBuffer[T] = SqueezeBuffer()
        for scope, parsed, payload in entries:
            key = (scope, parsed.pattern)
            indices = buffer.seen.get(key)
            if not indices:
                buffer.seen[key] = [len(buffer.items)]
                buffer.items.append(payload)
                buffer.parsed_meta.append(parsed)
                continue
            strategy = self.squeeze_strategies[parsed.kind]
            strategy.apply(buffer, key, indices, parsed, payload)
        return buffer.items
