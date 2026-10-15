"""Collision-fallback output resolver via progressive inheritance over base.OutputResolver."""

from collections.abc import Sequence
from pathlib import Path

from zipdir.models import ResolvedOutput
from zipdir.output.base import OutputResolver as BaseOutputResolver


class OutputResolver(BaseOutputResolver):
    """Extends base OutputResolver with timestamp collision fallback and bare `-o` CLI normalization."""

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

    def _build_dynamic_output(
        self,
        base_dir: Path,
        stem: str,
        *,
        timestamp: bool,
        force: bool,
    ) -> ResolvedOutput:
        res = super()._build_dynamic_output(base_dir, stem, timestamp=timestamp, force=force)
        if not timestamp and not force and (res.path.exists() or res.path.is_symlink()):
            fallback_path = base_dir / f"{stem}_{self.timestamp_fn()}.zip"
            return ResolvedOutput(path=fallback_path, explicit_zip=False, stem=stem, fell_back=True)
        return res
