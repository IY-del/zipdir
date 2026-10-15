"""Interfaces and FactoryMethod metaclass for terminal/UI reporting."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from zipdir.interfaces.models import DPackagerConfig, DPreset, MInterface


class MReporter(MInterface):
    """FactoryMethod metaclass for IReporter."""

    def __call__(cls, *args: object, **kwargs: object) -> "IReporter":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DReporter:
    """State invariant for terminal/UI reporters."""

    use_color: bool


class IReporter(DReporter, metaclass=MReporter):
    """Nominal interface for reporting preset listings, dry-run previews, and summaries."""

    def print_presets(self, presets: Mapping[str, DPreset]) -> None:
        raise NotImplementedError

    def print_dry_run(
        self,
        config: DPackagerConfig,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError

    def print_summary(
        self,
        config: DPackagerConfig,
        output: Path,
        entries: Sequence[tuple[Path, str]],
        rescued_files: Sequence[tuple[str, str]],
        excluded_files: Sequence[str],
    ) -> None:
        raise NotImplementedError
