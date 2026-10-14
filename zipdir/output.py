"""Output path resolution with 3-tier prefix semantics and timestamp collision fallback."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResolvedOutput:
    """Resolved archive output path and collision metadata."""

    path: Path
    explicit_zip: bool
    stem: str
    fell_back: bool = False


class OutputResolver:
    """Resolves archive output paths according to prefix rules and collision fallback.

    Prefix conventions for `-o` / `output_target`:
    - `None` (omitted): Current working directory (`./<name>.zip`)
    - `""` or `"?"` or `"?/"` (or bare `-o`): Source parent directory (`<source.parent>/<name>.zip`)
    - `"/..."` or `"~/..."`: Absolute path
    - `"./..."` or `"../..."` (or `"."`, `".."`): Current working directory relative path
    - `"___"` or `"___/..."` (optionally prefixed with `?` or `?/`): Source parent relative path

    Collision fallback:
    - When an explicit `.zip` filename is given (`-o foo.zip`), the filename is locked (no `-t` fallback).
    - When omitted or specifying a directory / stem without `.zip`, if `<stem>.zip` already exists and
      `force=False`, automatically falls back to `<stem>_<YYYYMMDD_HHMMSS>.zip`.
    """

    cwd: Path
    timestamp_fn: Callable[[], str]

    def __init__(
        self,
        cwd: Path | None = None,
        timestamp_fn: Callable[[], str] | None = None,
    ) -> None:
        self.cwd = cwd if cwd is not None else Path.cwd()
        self.timestamp_fn = timestamp_fn or (lambda: time.strftime("%Y%m%d_%H%M%S"))

    def normalize_cli_args(self, args: Sequence[str]) -> list[str]:
        """Normalize CLI arguments so bare `-o` / `--output` defaults to `?` (source.parent)."""
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
                    normalized.append("?")
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
        """Classify raw output string into (target_path, is_forced_dir) across 3 prefix tiers."""
        if raw in ("", "?", "?/"):
            return source.parent, True
        if raw.startswith("/") or raw == "~" or raw.startswith("~/"):
            return Path(raw).expanduser(), raw.endswith("/")
        if raw in (".", "..") or raw.startswith("./") or raw.startswith("../"):
            return self.cwd / raw, raw in (".", "..") or raw.endswith("/")

        rel = raw.removeprefix("?/").removeprefix("?")
        target_path = source.parent / rel if rel else source.parent
        return target_path, not rel or raw.endswith("/")

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
