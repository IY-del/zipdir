"""Interface and FactoryMethod metaclass for glob pattern compilation."""

import re
from collections.abc import Callable, Mapping

from zipdir.models.interface import MInterface


class MGlobCompiler(MInterface):
    """FactoryMethod metaclass for IGlobCompiler."""

    def __call__(cls, *args: object, **kwargs: object) -> "IGlobCompiler":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DGlobCompiler:
    """State invariant for gitignore glob compilers."""

    token_pattern: re.Pattern[str]
    translators: Mapping[str, Callable[[str], str]]


class IGlobCompiler(DGlobCompiler, metaclass=MGlobCompiler):
    """Nominal interface for compiling gitignore-style glob patterns into regular expressions."""

    def interpret(self, pattern: str) -> tuple[re.Pattern[str], bool, bool]:
        raise NotImplementedError
