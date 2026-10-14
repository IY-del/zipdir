"""Terminal styling, size formatting, and console reporting."""

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from zipdir.models import PackagerConfig, PresetModel

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


def format_size(num_bytes: int | float) -> str:
    """Format byte size into human-readable units."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0:
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


class ConsoleReporter:
    """Renders packaging summaries, dry-run previews, and preset listings to the terminal."""

    def print_presets(self, presets: Mapping[str, PresetModel]) -> None:
        """Display available presets and their configurations."""
        print(color_bold("\nAvailable zipdir presets:\n"))
        for name, p in presets.items():
            src_info = f"({p.source_path})" if p.source_path else "(built-in)"
            extends_info = f" [extends {', '.join(p.extends)}]" if p.extends else ""
            print(
                f"  {color_cyan(name):<12} {color_bold(p.description)}{color_dim(extends_info)} {color_dim(src_info)}"
            )
            if p.rules:
                rules_str = ", ".join(p.rules)
                print(f"    {color_dim('• Rules:')} {rules_str}")
            print()

    def print_dry_run(
        self,
        config: PackagerConfig,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        """Render dry-run preview of archive structure."""
        print(
            f"\n{color_yellow('[DRY RUN]')} Resulting archive structure for {color_bold(config.output.name)}:"
        )
        print(f"  • Source:   {config.source}")
        print(f"  • Preset:   {config.preset_name}")
        print(f"  • Rules:    {len(config.rules)} rules\n")
        if rescued_files:
            print(color_cyan("Rescued / Remapped files (!):"))
            for src, dst in rescued_files:
                print(f"  ↑ {src} -> {dst}")
        if excluded_files:
            print(color_yellow("Excluded paths:"))
            for ex in excluded_files:
                print(f"  ✕ {ex}")
        print(color_bold("Archive members:"))
        for _, arcname in entries:
            print(f"  + {arcname}")

    def print_summary(
        self,
        config: PackagerConfig,
        output: Path,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        """Render completion summary after archive creation."""
        file_count = sum(1 for _, arcname in entries if not arcname.endswith("/"))
        dir_count = sum(1 for _, arcname in entries if arcname.endswith("/"))
        size_str = format_size(output.stat().st_size)

        print(
            f"{color_success('✔')} Created archive: {color_bold(output.name)} {color_dim(f'({size_str})')}"
        )
        print(f"  {color_dim('Path:')}     {color_cyan(str(output))}")
        print(f"  {color_dim('Preset:')}   {config.preset_name} ({len(config.rules)} rules)")
        print(f"  {color_dim('Members:')}  {file_count} files, {dir_count} directories")

        if config.verbose:
            if rescued_files:
                print(f"\n{color_cyan('Rescued / Remapped files (!):')}")
                for src, dst in rescued_files:
                    print(f"  ↑ {src} -> {dst}")
            if excluded_files:
                print(f"{color_yellow('Excluded paths:')}")
                for ex in excluded_files:
                    print(f"  ✕ {ex}")
