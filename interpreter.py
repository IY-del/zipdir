"""4-component pattern matching and rule interpretation."""

import re

from zipdir.glob import GlobExpression
from zipdir.models import IgnoreRule, ParsedRule, RuleKind

# 4 components of rule syntax: [b1]{to}![pattern]
# 1. b1: leading '!' (redelete flag)
# 2. to: destination string ({to})
# 3. '!': separator
# 4. pattern: glob pattern ({pattern})
RULE_COMPONENT_PATTERN = re.compile(r"^(?P<b1>!?)(?P<to>[^!]*)!(?P<pattern>.+)$")


class RuleInterpreter:
    """Interprets .zipignore lines by matching the 4 components (!, {to}, !, {pattern})
    and determining RuleKind directly by the count of '!' marks with shorthand normalization.
    """

    def __init__(self, glob_compiler: GlobExpression | None = None) -> None:
        self.glob_compiler = glob_compiler or GlobExpression()

    def parse_components(self, line: str) -> ParsedRule | None:
        """Parse raw line into 4-component AST node (ParsedRule)."""
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None
        if stripped.startswith(r"\!"):
            return ParsedRule(RuleKind.EXCLUDE, "", stripped)

        m = RULE_COMPONENT_PATTERN.match(stripped)
        if not m:
            # 0 bangs -> EXCLUDE
            return ParsedRule(RuleKind.EXCLUDE, "", stripped)

        b1 = m.group("b1")
        to = m.group("to").strip()
        pattern = m.group("pattern").strip()
        if not pattern:
            return None

        # Count of '!' marks determines RuleKind: 1 = RESCUE, 2 = REDELETE
        bang_count = 2 if b1 else 1
        kind = RuleKind(bang_count)

        # Normalize shorthand: 1-bang rule without explicit {to} (!pattern) defaults to exile '?'
        target = to if (to or kind == RuleKind.REDELETE) else "?"

        return ParsedRule(kind, target, pattern)

    def interpret(self, line: str) -> IgnoreRule | None:
        """Parse and compile a raw rule line into an IgnoreRule."""
        parsed = self.parse_components(line)
        if parsed is None or not parsed.pattern:
            return None

        regex, is_dir_only, has_slash = self.glob_compiler.interpret(parsed.pattern)

        return IgnoreRule(
            raw=line,
            kind=parsed.kind,
            target=parsed.target,
            pattern=parsed.pattern,
            regex=regex,
            is_dir_only=is_dir_only,
            has_slash=has_slash,
        )


_DEFAULT_INTERPRETER = RuleInterpreter()


def compile_rule(line: str) -> IgnoreRule | None:
    """Parse a single rule using RuleInterpreter:
    - Exclude:    'pattern' (0 bangs)
    - Rescue:     '{to}!{pattern}' (1 bang) with default destination '?' for '!{pattern}'
                  - './!{pattern}': keep original directory hierarchy (階層死守)
                  - '?/!{pattern}' or '!{pattern}': exile / lift out of excluded parent (亡命ルート)
                  - '{dir}!{pattern}': remap to specified directory
    - Re-delete:  '!{to}!{pattern}' or '!!{pattern}' (2 bangs, cancels rescue, re-excludes items)
    """
    return _DEFAULT_INTERPRETER.interpret(line)
