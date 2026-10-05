"""Terminal styling and UI helpers."""

import os
import sys

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if USE_COLOR else text


def color_success(text: str) -> str:
    return _c(text, "1;32")


def color_dim(text: str) -> str:
    return _c(text, "2")


def color_bold(text: str) -> str:
    return _c(text, "1")


def color_cyan(text: str) -> str:
    return _c(text, "36")


def color_yellow(text: str) -> str:
    return _c(text, "33")
