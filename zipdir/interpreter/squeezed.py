"""Squeezed rule interpreter via progressive inheritance over base.RuleInterpreter."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.glob import IGlobCompiler, MGlobCompiler
from zipdir.interfaces.interpreter import IRuleSqueezer, ISqueezeStrategy
from zipdir.interfaces.models import DIgnoreRule, DParsedRule, DScopedRule, RuleKind
from zipdir.interpreter.base import RuleInterpreter as BaseRuleInterpreter
from zipdir.interpreter.strategies import DEFAULT_SQUEEZE_STRATEGIES, SqueezeBuffer
from zipdir.models import IgnoreRule, ParsedRule, ScopedRule

type _StagedCompileEntry = tuple[str, DParsedRule, PurePosixPath] | IgnoreRule


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
        normalized = [
            entry
            for item in rules
            if (entry := self._normalize_squeeze_item(item)) is not None
        ]
        return self._squeeze_staged(normalized)

    def compile_all(
        self, rules: Sequence[str | DScopedRule | DIgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects."""
        if not squeeze:
            return super().compile_all(rules)

        normalized = [
            entry
            for item in rules
            if (entry := self._normalize_compile_item(item)) is not None
        ]
        staged = self._squeeze_staged(normalized)
        return tuple(
            entry if isinstance(entry, IgnoreRule) else self._build_rule(*entry) for entry in staged
        )

    def _normalize_squeeze_item(
        self, item: str | DScopedRule
    ) -> tuple[PurePosixPath, DParsedRule, str | ScopedRule] | None:
        scope = item.scope if isinstance(item, DScopedRule) else PurePosixPath()
        line = item.rule if isinstance(item, DScopedRule) else item
        parsed = self.parse_components(line)
        if parsed is None:
            return None
        out_item: str | ScopedRule = (
            item
            if isinstance(item, (str, ScopedRule))
            else ScopedRule(scope=item.scope, rule=item.rule)
        )
        return scope, parsed, out_item

    def _normalize_compile_item(
        self, item: str | DScopedRule | DIgnoreRule
    ) -> tuple[PurePosixPath, DParsedRule, _StagedCompileEntry] | None:
        if isinstance(item, DIgnoreRule):
            concrete = (
                item
                if isinstance(item, IgnoreRule)
                else IgnoreRule(
                    raw=item.raw,
                    kind=item.kind,
                    target=item.target,
                    pattern=item.pattern,
                    regex=item.regex,
                    is_dir_only=item.is_dir_only,
                    has_slash=item.has_slash,
                    scope=item.scope,
                )
            )
            return concrete.scope, ParsedRule(concrete.kind, concrete.target, concrete.pattern), concrete

        scope = item.scope if isinstance(item, DScopedRule) else PurePosixPath()
        line = item.rule if isinstance(item, DScopedRule) else item
        parsed = self.parse_components(line)
        if parsed is None:
            return None
        return scope, parsed, (line, parsed, scope)

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
            self.squeeze_strategies[parsed.kind].apply(buffer, key, indices, parsed, payload)
        return buffer.items
