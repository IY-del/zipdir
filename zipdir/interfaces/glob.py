"""Interface for glob expression compilation."""

import re


class IGlobCompiler:
    """Interface for compiling glob expressions into regex patterns."""

    def compile(self, pattern: str) -> re.Pattern[str]:
        raise NotImplementedError
