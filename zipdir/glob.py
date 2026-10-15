"""Glob pattern compilation for gitignore-style patterns using token translation strategies."""

import re
from collections.abc import Callable, Mapping

from zipdir.models import IGlobCompiler

# Gitignore glob tokens in priority order:
# 1. '/**/' or '**/' -> directory recursive wildcard
# 2. '**' -> recursive wildcard
# 3. '*' -> single segment wildcard
# 4. '?' -> single non-slash character
# 5. '[...]' -> character class
# 6. '\.' -> escaped character
# 7. regex metacharacters -> escaped
# 8. literals and path separator
GLOB_TOKEN_REGEX = re.compile(
    r"""
    (?P<globstar_slash>\*\*/)|
    (?P<globstar>\*\*)|
    (?P<star>\*)|
    (?P<question>\?)|
    (?P<bracket>\[(!|\^)?.*?\])|
    (?P<escape>\\.)|
    (?P<meta>[.+()^${}|])|
    (?P<literal>[^\\*?\[.+()^${}|/]+)|
    (?P<slash>/)
    """,
    re.VERBOSE,
)


def _translate_bracket(token: str) -> str:
    inner = token[1:-1]
    return f"[^{inner[1:]}]" if inner.startswith("!") else token


DEFAULT_TOKEN_TRANSLATORS: dict[str, Callable[[str], str]] = {
    "globstar_slash": lambda _: "(?:.*/)?",
    "globstar": lambda _: ".*",
    "star": lambda _: "[^/]*",
    "question": lambda _: "[^/]",
    "bracket": _translate_bracket,
    "escape": lambda token: re.escape(token[1:]),
    "meta": lambda token: "\\" + token,
    "literal": lambda token: token,
    "slash": lambda token: token,
}


class GlobExpression(IGlobCompiler):
    """Interprets gitignore-style glob pattern into a compiled regex and metadata."""

    token_pattern: re.Pattern[str]
    translators: Mapping[str, Callable[[str], str]]

    def __init__(
        self,
        token_pattern: re.Pattern[str] = GLOB_TOKEN_REGEX,
        translators: Mapping[str, Callable[[str], str]] | None = None,
    ) -> None:
        self.token_pattern = token_pattern
        self.translators = translators if translators is not None else DEFAULT_TOKEN_TRANSLATORS

    def interpret(self, pattern: str) -> tuple[re.Pattern[str], bool, bool]:
        """Compile a glob pattern into (compiled_regex, is_dir_only, has_slash)."""
        is_dir_only = pattern.endswith("/")
        clean_pat = pattern[:-1] if is_dir_only else pattern
        anchored = clean_pat.startswith("/")
        if anchored:
            clean_pat = clean_pat[1:]
        has_slash = "/" in clean_pat

        regex_body = self.token_pattern.sub(self._translate_token, clean_pat)
        full_regex = f"^{regex_body}$" if (has_slash or anchored) else f"(?:^|/){regex_body}$"

        return re.compile(full_regex), is_dir_only, has_slash

    def _translate_token(self, match: re.Match[str]) -> str:
        """Translate a single glob token by dispatching to its registered strategy."""
        group_name = match.lastgroup
        token = match.group(0)
        if group_name is not None and (translator := self.translators.get(group_name)) is not None:
            return translator(token)
        return token
