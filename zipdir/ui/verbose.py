"""Verbose console reporter via progressive inheritance over base.ConsoleReporter."""

from collections.abc import Sequence
from pathlib import Path

from zipdir.interfaces.models import DPackagerConfig
from zipdir.ui.base import ConsoleReporter as BaseConsoleReporter


class ConsoleReporter(BaseConsoleReporter):
    """Extends base ConsoleReporter with verbose breakdown of rescued and excluded items."""

    def print_summary(
        self,
        config: DPackagerConfig,
        output: Path,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        super().print_summary(config, output, entries, rescued_files, excluded_files)
        if config.verbose:
            if rescued_files:
                print(f"\n{self._cyan('Rescued / Remapped files (!):')}")
                for src, dst in rescued_files:
                    print(f"  ↑ {src} -> {dst}")
            if excluded_files:
                print(f"{self._yellow('Excluded paths:')}")
                for ex in excluded_files:
                    print(f"  ✕ {ex}")
