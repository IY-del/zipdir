"""Minimal concrete 4-component .zipignore rule interpreter (base stage for progressive inheritance)."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.glob.interface import IGlobCompiler, MGlobCompiler
from zipdir.interpreter.interface import IRuleInterpreter
from zipdir.models import (
    DIgnoreRule,
    DParsedRule,
    DScopedRule,
    IgnoreRule,
    ParsedRule,
    RuleKind,
)

# 4 components of rule syntax: [b1]{to}![pattern]
# 1. b1: leading '!' (redelete flag)
# 2. to: destination string ({to})
# 3. '!': separator
# 4. pattern: glob pattern ({pattern})
RULE_COMPONENT_PATTERN = re.compile(r"^(?P<b1>!?)(?P<to>[^!]*)!(?P<pattern>.+)$")


class RuleInterpreter(IRuleInterpreter):
    """Minimal concrete interpreter that parses 4-component syntax and compiles .zipignore rules."""

    glob_compiler: IGlobCompiler

    def __init__(
        self,
        glob_compiler: IGlobCompiler | None = None,
        create_glob: MGlobCompiler = IGlobCompiler,
    ) -> None:
        self.glob_compiler = glob_compiler or create_glob()

    def parse_components(self, line: str) -> ParsedRule | None:
        """Parse raw line into 4-component AST node (ParsedRule)."""
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
        if parsed is None:
            return None
        return self._build_rule(line, parsed, scope)

    def compile_all(
        self, rules: Sequence[str | DScopedRule | DIgnoreRule]
    ) -> tuple[IgnoreRule, ...]:
        """Compile a sequence of raw or scoped rules into IgnoreRule objects."""
        compiled: list[IgnoreRule] = []
        for item in rules:
            if isinstance(item, IgnoreRule):
                compiled.append(item)
            elif isinstance(item, DIgnoreRule):
                compiled.append(
                    IgnoreRule(
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
            elif isinstance(item, DScopedRule):
                if (r := self.interpret(item.rule, scope=item.scope)) is not None:
                    compiled.append(r)
            elif (r := self.interpret(item)) is not None:
                compiled.append(r)
        return tuple(compiled)

    def _build_rule(self, raw: str, parsed: DParsedRule, scope: PurePosixPath) -> IgnoreRule:
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
