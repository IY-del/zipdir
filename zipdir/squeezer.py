"""Compile-time rule squeezing via progressive inheritance over RuleInterpreter."""

from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.interpreter import RuleInterpreter as BaseRuleInterpreter
from zipdir.models import IgnoreRule, ParsedRule, ScopedRule


class RuleInterpreter(BaseRuleInterpreter):
    """Extends base RuleInterpreter with compile-time phagocytosis (rule squeezing)."""

    def squeeze(self, rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
        """Squeeze rule lines by pattern and scope: later rules with identical patterns
        within the same scope eat earlier rules (compile-time phagocytosis).
        """
        squeezed: list[str | ScopedRule] = []
        seen: dict[tuple[PurePosixPath, str], int] = {}
        for item in rules:
            scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
            line = item.rule if isinstance(item, ScopedRule) else item
            parsed = self.parse_components(line)
            if parsed is None:
                continue
            key = (scope, parsed.pattern)
            if key in seen:
                squeezed[seen[key]] = item
            else:
                seen[key] = len(squeezed)
                squeezed.append(item)
        return squeezed

    def compile_all(
        self, rules: Sequence[str | ScopedRule | IgnoreRule], *, squeeze: bool = False
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects.

        When `squeeze=True`, performs compile-time phagocytosis by (scope, pattern) in a
        single pass without re-parsing rule strings.
        """
        if not squeeze:
            return super().compile_all(rules)

        staged: list[tuple[str, ParsedRule, PurePosixPath] | IgnoreRule] = []
        seen: dict[tuple[PurePosixPath, str], int] = {}

        for item in rules:
            if isinstance(item, IgnoreRule):
                key = (item.scope, item.pattern)
                entry: tuple[str, ParsedRule, PurePosixPath] | IgnoreRule = item
            else:
                scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
                line = item.rule if isinstance(item, ScopedRule) else item
                parsed = self.parse_components(line)
                if parsed is None or not parsed.pattern:
                    continue
                key = (scope, parsed.pattern)
                entry = (line, parsed, scope)

            if key in seen:
                staged[seen[key]] = entry
            else:
                seen[key] = len(staged)
                staged.append(entry)

        return tuple(
            entry if isinstance(entry, IgnoreRule) else self._build_rule(*entry) for entry in staged
        )


def squeeze_rules(rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
    """Squeeze rule lines by pattern and scope."""
    return RuleInterpreter().squeeze(rules)


__all__ = ["RuleInterpreter", "squeeze_rules"]
