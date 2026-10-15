"""Concrete 3-tier output target classification strategies."""

from pathlib import Path

from zipdir.interfaces.output import IOutputTargetStrategy


class BareParentOutputStrategy(IOutputTargetStrategy):
    """Concrete Strategy for bare `-o` (`""`): resolves to `<source.parent>/` directory."""

    def matches(self, raw: str) -> bool:
        return raw == ""

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return source.parent, True


class AbsoluteOutputStrategy(IOutputTargetStrategy):
    """Concrete Strategy for `/...` or `~` / `~/...`: resolves as an absolute filesystem path."""

    def matches(self, raw: str) -> bool:
        return raw.startswith("/") or raw == "~" or raw.startswith("~/")

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return Path(raw).expanduser(), raw.endswith("/")


class CwdRelativeOutputStrategy(IOutputTargetStrategy):
    """Concrete Strategy for `.`, `..`, `./...`, or `../...`: resolves relative to cwd."""

    def matches(self, raw: str) -> bool:
        return raw in (".", "..") or raw.startswith("./") or raw.startswith("../")

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return cwd / raw, raw in (".", "..") or raw.endswith("/")


class ParentRelativeOutputStrategy(IOutputTargetStrategy):
    """Concrete fallback Strategy (`___` without prefix): resolves relative to `<source.parent>`."""

    def matches(self, raw: str) -> bool:
        return True

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return source.parent / raw, raw.endswith("/")


DEFAULT_OUTPUT_TARGET_STRATEGIES: tuple[IOutputTargetStrategy, ...] = (
    BareParentOutputStrategy(),
    AbsoluteOutputStrategy(),
    CwdRelativeOutputStrategy(),
    ParentRelativeOutputStrategy(),
)
