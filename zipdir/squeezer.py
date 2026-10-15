"""Compile-time rule squeezing via Strategy and progressive inheritance over RuleInterpreter."""

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from zipdir.interpreter import (
    RuleInterpreter as BaseRuleInterpreter,
)
from zipdir.interpreter import (
    redelete_matches_rescue,
)
from zipdir.models import (
    IGlobCompiler,
    IgnoreRule,
    IRuleSqueezer,
    ParsedRule,
    RuleKind,
    ScopedRule,
)


class DSqueezeBuffer[T]:
    """Mutable buffer state invariant for compile-time rule squeezing."""

    items: list[T]
    parsed_meta: list[ParsedRule]
    seen: dict[tuple[PurePosixPath, str], list[int]]

    def __init__(self) -> None:
        self.items = []
        self.parsed_meta = []
        self.seen = {}

    def shift_indices(self, removed_idx: int) -> None:
        """Adjust recorded index positions after an element removal."""
        for key, idx_list in self.seen.items():
            self.seen[key] = [i - 1 if i > removed_idx else i for i in idx_list if i != removed_idx]


class ISqueezeStrategy:
    """Nominal Strategy interface for resolving rule collisions on identical (scope, pattern)."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: ParsedRule,
        entry: T,
    ) -> None:
        raise NotImplementedError


class OverwriteSqueezeStrategy(ISqueezeStrategy):
    """Strategy for EXCLUDE and RESCUE: engulfs all prior rules sharing (scope, pattern)."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: ParsedRule,
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
    """Strategy for REDELETE: replaces matching-target RESCUE/REDELETE or appends independently."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: ParsedRule,
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
        parsed_meta: list[ParsedRule],
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
        normalized: list[tuple[PurePosixPath, ParsedRule, str | ScopedRule]] = []
        for item in rules:
            scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
            line = item.rule if isinstance(item, ScopedRule) else item
            parsed = self.parse_components(line)
            if parsed is not None:
                normalized.append((scope, parsed, item))
        return self._squeeze_staged(normalized)

    def compile_all(
        self, rules: Sequence[str | ScopedRule | IgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects.

        When `squeeze=True`, performs target-aware compile-time phagocytosis by (scope, pattern).
        """
        if not squeeze:
            return super().compile_all(rules)

        type StagedEntry = tuple[str, ParsedRule, PurePosixPath] | IgnoreRule
        normalized: list[tuple[PurePosixPath, ParsedRule, StagedEntry]] = []
        for item in rules:
            if isinstance(item, IgnoreRule):
                parsed = ParsedRule(item.kind, item.target, item.pattern)
                normalized.append((item.scope, parsed, item))
            else:
                scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
                line = item.rule if isinstance(item, ScopedRule) else item
                parsed_opt = self.parse_components(line)
                if parsed_opt is not None:
                    normalized.append((scope, parsed_opt, (line, parsed_opt, scope)))

        staged = self._squeeze_staged(normalized)
        return tuple(
            entry if isinstance(entry, IgnoreRule) else self._build_rule(*entry) for entry in staged
        )

    def _squeeze_staged[T](
        self, entries: Sequence[tuple[PurePosixPath, ParsedRule, T]]
    ) -> list[T]:
        """Template skeleton that squeezes normalized rule entries using RuleKind strategies."""
        buffer: DSqueezeBuffer[T] = DSqueezeBuffer()
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


def squeeze_rules(rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
    """Squeeze rule lines by pattern and scope."""
    return RuleInterpreter().squeeze(rules)


__all__ = [
    "DEFAULT_SQUEEZE_STRATEGIES",
    "DSqueezeBuffer",
    "ISqueezeStrategy",
    "OverwriteSqueezeStrategy",
    "RuleInterpreter",
    "TargetedRedeleteSqueezeStrategy",
    "squeeze_rules",
]
