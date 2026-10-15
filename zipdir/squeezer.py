"""Concrete compile-time rule squeezing via Strategy and progressive inheritance."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interfaces import (
    DIgnoreRule,
    DParsedRule,
    DScopedRule,
    DSqueezeBuffer,
    IGlobCompiler,
    IRuleSqueezer,
    ISqueezeStrategy,
    MGlobCompiler,
    RuleKind,
)
from zipdir.interpreter import RuleInterpreter as BaseRuleInterpreter
from zipdir.models import (
    IgnoreRule,
    ParsedRule,
    ScopedRule,
    SqueezeBuffer,
    redelete_matches_rescue,
)


class OverwriteSqueezeStrategy(ISqueezeStrategy):
    """Concrete Strategy for EXCLUDE and RESCUE: engulfs all prior rules sharing (scope, pattern)."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: DParsedRule,
        entry: T,
    ) -> None:
        primary_idx = indices[0]
        buffer.items[primary_idx] = entry
        buffer.parsed_meta[primary_idx] = parsed
        if len(indices) > 1:
            for drop_idx in sorted(indices[1:], reverse=True):
                del buffer.items[drop_idx]
                del buffer.parsed_meta[drop_idx]
                buffer.shift_indices(drop_idx)
            buffer.seen[key] = [buffer.seen[key][0]]


class TargetedRedeleteSqueezeStrategy(ISqueezeStrategy):
    """Concrete Strategy for REDELETE: replaces matching-target RESCUE/REDELETE or appends."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: DParsedRule,
        entry: T,
    ) -> None:
        matched_idx = self._find_matching_index(parsed.target, indices, buffer.parsed_meta)
        if matched_idx is not None:
            buffer.items[matched_idx] = entry
            buffer.parsed_meta[matched_idx] = parsed
        else:
            indices.append(len(buffer.items))
            buffer.items.append(entry)
            buffer.parsed_meta.append(parsed)

    def _find_matching_index(
        self,
        redelete_target: str,
        indices: list[int],
        parsed_meta: Sequence[DParsedRule],
    ) -> int | None:
        for idx in reversed(indices):
            candidate = parsed_meta[idx]
            if candidate.kind in (RuleKind.RESCUE, RuleKind.REDELETE) and redelete_matches_rescue(
                redelete_target, candidate.target
            ):
                return idx
        return None


DEFAULT_SQUEEZE_STRATEGIES: dict[RuleKind, ISqueezeStrategy] = {
    RuleKind.EXCLUDE: OverwriteSqueezeStrategy(),
    RuleKind.RESCUE: OverwriteSqueezeStrategy(),
    RuleKind.REDELETE: TargetedRedeleteSqueezeStrategy(),
}


class RuleInterpreter(BaseRuleInterpreter, IRuleSqueezer):
    """Concrete squeezer extending base RuleInterpreter via progressive inheritance."""

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


def squeeze_rules(rules: Sequence[str | DScopedRule]) -> list[str | ScopedRule]:
    """Squeeze rule lines by pattern and scope."""
    return RuleInterpreter().squeeze(rules)


__all__ = [
    "DEFAULT_SQUEEZE_STRATEGIES",
    "OverwriteSqueezeStrategy",
    "RuleInterpreter",
    "TargetedRedeleteSqueezeStrategy",
    "squeeze_rules",
]
