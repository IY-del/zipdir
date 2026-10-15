"""Output path resolution with 3-tier prefix Strategy and timestamp collision fallback."""

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from zipdir.models import IOutputResolver, ResolvedOutput


class IOutputTargetStrategy:
    """Nominal Strategy interface for classifying 3-tier raw output path prefixes."""

    def matches(self, raw: str) -> bool:
        raise NotImplementedError

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        raise NotImplementedError


class BareParentOutputStrategy(IOutputTargetStrategy):
    """Matches bare `-o` (`""`): resolves to `<source.parent>/` directory."""

    def matches(self, raw: str) -> bool:
        return raw == ""

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return source.parent, True


class AbsoluteOutputStrategy(IOutputTargetStrategy):
    """Matches `/...` or `~` / `~/...`: resolves as an absolute filesystem path."""

    def matches(self, raw: str) -> bool:
        return raw.startswith("/") or raw == "~" or raw.startswith("~/")

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return Path(raw).expanduser(), raw.endswith("/")


class CwdRelativeOutputStrategy(IOutputTargetStrategy):
    """Matches `.`, `..`, `./...`, or `../...`: resolves relative to current working directory."""

    def matches(self, raw: str) -> bool:
        return raw in (".", "..") or raw.startswith("./") or raw.startswith("../")

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        return cwd / raw, raw in (".", "..") or raw.endswith("/")


class ParentRelativeOutputStrategy(IOutputTargetStrategy):
    """Default fallback strategy (`___` without prefix): resolves relative to `<source.parent>`."""

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


class OutputResolver(IOutputResolver):
    """Resolves archive output paths according to 3-tier prefix rules and collision fallback."""

    cwd: Path
    timestamp_fn: Callable[[], str]
    target_strategies: Sequence[IOutputTargetStrategy]

    def __init__(
        self,
        cwd: Path | None = None,
        timestamp_fn: Callable[[], str] | None = None,
        target_strategies: Sequence[IOutputTargetStrategy] | None = None,
    ) -> None:
        self.cwd = cwd if cwd is not None else Path.cwd()
        self.timestamp_fn = timestamp_fn or (lambda: time.strftime("%Y%m%d_%H%M%S"))
        self.target_strategies = (
            target_strategies
            if target_strategies is not None
            else DEFAULT_OUTPUT_TARGET_STRATEGIES
        )

    def normalize_cli_args(self, args: Sequence[str]) -> list[str]:
        """Normalize CLI arguments so bare `-o` / `--output` defaults to `""` (source.parent)."""
        normalized: list[str] = []
        after_double_dash = False
        i = 0
        n = len(args)
        while i < n:
            arg = args[i]
            if after_double_dash:
                normalized.append(arg)
                i += 1
                continue
            if arg == "--":
                after_double_dash = True
                normalized.append(arg)
                i += 1
                continue
            if arg in ("-o", "--output"):
                normalized.append(arg)
                if i + 1 >= n or args[i + 1].startswith("-"):
                    normalized.append("")
                i += 1
                continue
            normalized.append(arg)
            i += 1
        return normalized

    def resolve_with_metadata(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> ResolvedOutput:
        """Resolve destination archive path and return ResolvedOutput metadata."""
        if output_target is None:
            base_dir = self.cwd.resolve()
            return self._build_dynamic_output(base_dir, name, timestamp=timestamp, force=force)

        raw = output_target.strip() if isinstance(output_target, str) else str(output_target)
        target_path, is_forced_dir = self._classify_target(source, raw)

        if raw.endswith(".zip") and not is_forced_dir:
            final_path = target_path.parent.resolve() / target_path.name
            return ResolvedOutput(
                path=final_path,
                explicit_zip=True,
                stem=final_path.stem,
                fell_back=False,
            )

        if is_forced_dir or target_path.is_dir():
            base_dir = target_path.resolve()
            stem = name
        else:
            base_dir = target_path.parent.resolve()
            stem = target_path.name

        return self._build_dynamic_output(base_dir, stem, timestamp=timestamp, force=force)

    def resolve(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> Path:
        """Resolve destination archive path."""
        return self.resolve_with_metadata(
            source,
            name,
            output_target,
            timestamp=timestamp,
            force=force,
        ).path

    def _classify_target(self, source: Path, raw: str) -> tuple[Path, bool]:
        """Classify raw output string into (target_path, is_forced_dir) via Strategy chain."""
        for strategy in self.target_strategies:
            if strategy.matches(raw):
                return strategy.classify(source, self.cwd, raw)
        return source.parent / raw, raw.endswith("/")

    def _build_dynamic_output(
        self,
        base_dir: Path,
        stem: str,
        *,
        timestamp: bool,
        force: bool,
    ) -> ResolvedOutput:
        if timestamp:
            ts_path = base_dir / f"{stem}_{self.timestamp_fn()}.zip"
            return ResolvedOutput(path=ts_path, explicit_zip=False, stem=stem, fell_back=False)

        primary_path = base_dir / f"{stem}.zip"
        if not force and (primary_path.exists() or primary_path.is_symlink()):
            fallback_path = base_dir / f"{stem}_{self.timestamp_fn()}.zip"
            return ResolvedOutput(path=fallback_path, explicit_zip=False, stem=stem, fell_back=True)

        return ResolvedOutput(path=primary_path, explicit_zip=False, stem=stem, fell_back=False)


def resolve_output_path(
    source: Path,
    name: str,
    output_target: str | Path | None,
    timestamp: bool = False,
    *,
    force: bool = False,
    cwd: Path | None = None,
) -> Path:
    """Resolve and normalize destination archive path (defaults to current working directory)."""
    return OutputResolver(cwd=cwd).resolve(
        source,
        name,
        output_target,
        timestamp=timestamp,
        force=force,
    )
