"""Glob pattern compilation for gitignore-style patterns using token translation."""

import re

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


class GlobExpression:
    """Interprets gitignore-style glob pattern into a compiled regex and metadata."""

    token_pattern: re.Pattern[str]

    def __init__(self, token_pattern: re.Pattern[str] = GLOB_TOKEN_REGEX) -> None:
        self.token_pattern = token_pattern

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
        """Translate a single glob token into its regex equivalent."""
        if match.group("globstar_slash"):
            return "(?:.*/)?"
        if match.group("globstar"):
            return ".*"
        if match.group("star"):
            return "[^/]*"
        if match.group("question"):
            return "[^/]"
        if bracket := match.group("bracket"):
            inner = bracket[1:-1]
            if inner.startswith("!"):
                return f"[^{inner[1:]}]"
            return bracket
        if escape := match.group("escape"):
            return re.escape(escape[1:])
        if meta := match.group("meta"):
            return "\\" + meta
        return match.group(0)
