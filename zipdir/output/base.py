"""Minimal concrete 3-tier output path resolver (base stage for progressive inheritance)."""

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from zipdir.interfaces.output import IOutputResolver, IOutputTargetStrategy
from zipdir.models import ResolvedOutput
from zipdir.output.strategies import DEFAULT_OUTPUT_TARGET_STRATEGIES


class OutputResolver(IOutputResolver):
    """Minimal concrete output path resolver using 3-tier prefix strategies."""

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
            target_strategies if target_strategies is not None else DEFAULT_OUTPUT_TARGET_STRATEGIES
        )

    def normalize_cli_args(self, args: Sequence[str]) -> list[str]:
        """Base CLI argument pass-through (extended in fallback.py)."""
        return list(args)

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
            return self._build_dynamic_output(
                self.cwd.resolve(), name, timestamp=timestamp, force=force
            )

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

        base_dir, stem = self._resolve_dir_and_stem(target_path, name, is_forced_dir=is_forced_dir)
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

    def _resolve_dir_and_stem(
        self, target_path: Path, default_name: str, *, is_forced_dir: bool
    ) -> tuple[Path, str]:
        if is_forced_dir or target_path.is_dir():
            return target_path.resolve(), default_name
        return target_path.parent.resolve(), target_path.name

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
        """Base dynamic output builder (extended with collision fallback in fallback.py)."""
        if timestamp:
            ts_path = base_dir / f"{stem}_{self.timestamp_fn()}.zip"
            return ResolvedOutput(path=ts_path, explicit_zip=False, stem=stem, fell_back=False)
        primary_path = base_dir / f"{stem}.zip"
        return ResolvedOutput(path=primary_path, explicit_zip=False, stem=stem, fell_back=False)
