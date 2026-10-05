"""Rule-level squeezing and pattern phagocytosis."""

from collections.abc import Sequence

from zipdir.interpreter import _DEFAULT_INTERPRETER


def squeeze_rules(rules: Sequence[str]) -> list[str]:
    """Squeeze rule lines by pattern: later rules with identical patterns eat earlier rules,
    resolving inheritance and local overrides (compile-time phagocytosis).
    """
    squeezed: list[str] = []
    seen: dict[str, int] = {}
    for line in rules:
        parsed = _DEFAULT_INTERPRETER.parse_components(line)
        if parsed is None:
            continue
        pat = parsed.pattern
        if pat in seen:
            idx = seen[pat]
            squeezed[idx] = line
        else:
            seen[pat] = len(squeezed)
            squeezed.append(line)
    return squeezed
