"""Compile-time rule squeezing via progressive inheritance over RuleInterpreter."""

from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.interpreter import (
    RuleInterpreter as BaseRuleInterpreter,
)
from zipdir.interpreter import (
    redelete_matches_rescue,
)
from zipdir.models import IgnoreRule, ParsedRule, RuleKind, ScopedRule


class RuleInterpreter(BaseRuleInterpreter):
    """Extends base RuleInterpreter with target-aware compile-time phagocytosis (rule squeezing)."""

    def squeeze(self, rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
        """Squeeze rule lines by pattern and scope with target-aware phagocytosis.

        Unconditional rules (EXCLUDE, RESCUE, or '!!' REDELETE) eat any earlier rule with
        the same (scope, pattern). Targeted REDELETE ('!?/{to}!pattern') eats an earlier
        RESCUE rule only if its target matches; otherwise both rules are preserved.
        """
        squeezed: list[str | ScopedRule] = []
        parsed_meta: list[ParsedRule] = []
        seen: dict[tuple[PurePosixPath, str], list[int]] = {}

        for item in rules:
            scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
            line = item.rule if isinstance(item, ScopedRule) else item
            parsed = self.parse_components(line)
            if parsed is None:
                continue
            key = (scope, parsed.pattern)
            indices = seen.get(key)

            if not indices:
                seen[key] = [len(squeezed)]
                squeezed.append(item)
                parsed_meta.append(parsed)
                continue

            if parsed.kind == RuleKind.REDELETE and parsed.target:
                matched_idx = self._find_matching_rescue_index(parsed.target, indices, parsed_meta)
                if matched_idx is not None:
                    squeezed[matched_idx] = item
                    parsed_meta[matched_idx] = parsed
                else:
                    indices.append(len(squeezed))
                    squeezed.append(item)
                    parsed_meta.append(parsed)
            else:
                primary_idx = indices[0]
                squeezed[primary_idx] = item
                parsed_meta[primary_idx] = parsed
                if len(indices) > 1:
                    for drop_idx in sorted(indices[1:], reverse=True):
                        del squeezed[drop_idx]
                        del parsed_meta[drop_idx]
                        self._shift_indices(seen, drop_idx)
                    seen[key] = [seen[key][0]]

        return squeezed

    def compile_all(
        self, rules: Sequence[str | ScopedRule | IgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects.

        When `squeeze=True`, performs target-aware compile-time phagocytosis by (scope, pattern).
        """
        if not squeeze:
            return super().compile_all(rules)

        staged: list[tuple[str, ParsedRule, PurePosixPath] | IgnoreRule] = []
        parsed_meta: list[ParsedRule] = []
        seen: dict[tuple[PurePosixPath, str], list[int]] = {}

        for item in rules:
            if isinstance(item, IgnoreRule):
                key = (item.scope, item.pattern)
                entry: tuple[str, ParsedRule, PurePosixPath] | IgnoreRule = item
                parsed = ParsedRule(item.kind, item.target, item.pattern)
            else:
                scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
                line = item.rule if isinstance(item, ScopedRule) else item
                parsed_opt = self.parse_components(line)
                if parsed_opt is None or not parsed_opt.pattern:
                    continue
                parsed = parsed_opt
                key = (scope, parsed.pattern)
                entry = (line, parsed, scope)

            indices = seen.get(key)
            if not indices:
                seen[key] = [len(staged)]
                staged.append(entry)
                parsed_meta.append(parsed)
                continue

            if parsed.kind == RuleKind.REDELETE and parsed.target:
                matched_idx = self._find_matching_rescue_index(parsed.target, indices, parsed_meta)
                if matched_idx is not None:
                    staged[matched_idx] = entry
                    parsed_meta[matched_idx] = parsed
                else:
                    indices.append(len(staged))
                    staged.append(entry)
                    parsed_meta.append(parsed)
            else:
                primary_idx = indices[0]
                staged[primary_idx] = entry
                parsed_meta[primary_idx] = parsed
                if len(indices) > 1:
                    for drop_idx in sorted(indices[1:], reverse=True):
                        del staged[drop_idx]
                        del parsed_meta[drop_idx]
                        self._shift_indices(seen, drop_idx)
                    seen[key] = [seen[key][0]]

        return tuple(
            entry if isinstance(entry, IgnoreRule) else self._build_rule(*entry) for entry in staged
        )

    def _find_matching_rescue_index(
        self,
        redelete_target: str,
        indices: list[int],
        parsed_meta: list[ParsedRule],
    ) -> int | None:
        for idx in reversed(indices):
            candidate = parsed_meta[idx]
            if candidate.kind == RuleKind.RESCUE and redelete_matches_rescue(
                redelete_target, candidate.target
            ):
                return idx
            if candidate.kind == RuleKind.REDELETE and candidate.target == redelete_target:
                return idx
        return None

    def _shift_indices(
        self, seen: dict[tuple[PurePosixPath, str], list[int]], removed_idx: int
    ) -> None:
        for key, idx_list in seen.items():
            seen[key] = [i - 1 if i > removed_idx else i for i in idx_list if i != removed_idx]


def squeeze_rules(rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
    """Squeeze rule lines by pattern and scope."""
    return RuleInterpreter().squeeze(rules)


__all__ = ["RuleInterpreter", "squeeze_rules"]
