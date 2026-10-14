"""4-component pattern matching and base rule compilation."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.glob import GlobExpression
from zipdir.models import IgnoreRule, ParsedRule, RuleKind, ScopedRule

# 4 components of rule syntax: [b1]{to}![pattern]
# 1. b1: leading '!' (redelete flag)
# 2. to: destination string ({to})
# 3. '!': separator
# 4. pattern: glob pattern ({pattern})
RULE_COMPONENT_PATTERN = re.compile(r"^(?P<b1>!?)(?P<to>[^!]*)!(?P<pattern>.+)$")


def normalize_target(target: str) -> str:
    """Normalize a rescue/redelete destination target into canonical form."""
    stripped = target.strip()
    if stripped == "":
        return ""
    if stripped in (".", "./"):
        return "./"
    if stripped in ("..", "../"):
        return "../"
    if stripped == "/":
        return "/"
    return stripped.rstrip("/")


def redelete_matches_rescue(redelete_target: str, rescued_target: str | None) -> bool:
    """Check whether a REDELETE target cancels a given RESCUE target."""
    if rescued_target is None:
        return True
    return normalize_target(redelete_target) == normalize_target(rescued_target)


class RuleInterpreter:
    """Base interpreter that parses 4-component syntax and compiles .zipignore rules."""

    glob_compiler: GlobExpression

    def __init__(self, glob_compiler: GlobExpression | None = None) -> None:
        self.glob_compiler = glob_compiler or GlobExpression()

    def parse_components(self, line: str) -> ParsedRule | None:
        """Parse raw line into 4-component AST node (ParsedRule).

        3-tier destination prefix rules for `{to}` in `[!]{to}!{pattern}`:
        - `/` (`/!`, `/{to}!`): Archive root
        - `./` or `../` (`./!`, `./{to}!`, `../!`): Original source / local scope hierarchy
        - omitted (`!`, `{to}!`): Exile destination (shallowest excluded ancestor's parent)

        Strict notation rules:
        - 0 bangs: EXCLUDE (`{pattern}`)
        - 1 bang:  RESCUE (`{to}!{pattern}`, `./!{pattern}`, `!{pattern}`)
        - 2 bangs: REDELETE (`!{to}!{pattern}`, `!./!{pattern}`, `!!{pattern}`)
        """
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return None
        if stripped.startswith(r"\!"):
            return ParsedRule(RuleKind.EXCLUDE, "", stripped)

        m = RULE_COMPONENT_PATTERN.match(stripped)
        if not m:
            return ParsedRule(RuleKind.EXCLUDE, "", stripped)

        b1 = m.group("b1")
        to = m.group("to").strip()
        pattern = m.group("pattern").strip()
        if not pattern or "?" in to:
            return None

        kind = RuleKind.REDELETE if b1 else RuleKind.RESCUE
        return ParsedRule(kind, to, pattern)

    def interpret(self, line: str, scope: PurePosixPath = PurePosixPath()) -> IgnoreRule | None:
        """Parse and compile a raw rule line into an IgnoreRule."""
        parsed = self.parse_components(line)
        if parsed is None or not parsed.pattern:
            return None
        return self._build_rule(line, parsed, scope)

    def compile_all(self, rules: Sequence[str | ScopedRule | IgnoreRule]) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects."""
        compiled: list[IgnoreRule] = []
        for item in rules:
            if isinstance(item, IgnoreRule):
                compiled.append(item)
            elif isinstance(item, ScopedRule):
                if (r := self.interpret(item.rule, scope=item.scope)) is not None:
                    compiled.append(r)
            elif (r := self.interpret(item)) is not None:
                compiled.append(r)
        return tuple(compiled)

    def _build_rule(self, raw: str, parsed: ParsedRule, scope: PurePosixPath) -> IgnoreRule:
        regex, is_dir_only, has_slash = self.glob_compiler.interpret(parsed.pattern)
        return IgnoreRule(
            raw=raw,
            kind=parsed.kind,
            target=parsed.target,
            pattern=parsed.pattern,
            regex=regex,
            is_dir_only=is_dir_only,
            has_slash=has_slash,
            scope=scope,
        )


def compile_rule(line: str, scope: PurePosixPath = PurePosixPath()) -> IgnoreRule | None:
    """Compile a single .zipignore rule line into an IgnoreRule."""
    return RuleInterpreter().interpret(line, scope=scope)
