"""Rule-level squeezing and pattern phagocytosis."""

from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.interpreter import _DEFAULT_INTERPRETER
from zipdir.models import ScopedRule


def squeeze_rules(rules: Sequence[str | ScopedRule]) -> list[str | ScopedRule]:
    """Squeeze rule lines by pattern and scope: later rules with identical patterns
    within the same scope eat earlier rules, resolving inheritance and local overrides
    (compile-time phagocytosis).
    """
    squeezed: list[str | ScopedRule] = []
    seen: dict[tuple[PurePosixPath, str], int] = {}
    for item in rules:
        scope = item.scope if isinstance(item, ScopedRule) else PurePosixPath()
        line = item.rule if isinstance(item, ScopedRule) else item
        parsed = _DEFAULT_INTERPRETER.parse_components(line)
        if parsed is None:
            continue
        pat = parsed.pattern
        key = (scope, pat)
        if key in seen:
            idx = seen[key]
            squeezed[idx] = item
        else:
            seen[key] = len(squeezed)
            squeezed.append(item)
    return squeezed
