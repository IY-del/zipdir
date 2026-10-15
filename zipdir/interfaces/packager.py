"""Interfaces and FactoryMethod metaclass for archive entry writing and packaging."""

import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

from zipdir.interfaces.evaluator import IPathEvaluator
from zipdir.interfaces.models import DIgnoreRule, DPackagerConfig, MInterface
from zipdir.interfaces.ui import IReporter


class IArchiveEntryWriter:
    """Nominal Strategy interface for writing an entry into a ZipFile archive."""

    def matches(self, item: Path, source: Path) -> bool:
        raise NotImplementedError

    def write(self, archive: zipfile.ZipFile, item: Path, arcname: str) -> None:
        raise NotImplementedError


class MPackager(MInterface):
    """FactoryMethod metaclass for IPackager."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPackager":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPackager:
    """State invariant for archive packagers."""

    config: DPackagerConfig
    evaluator: IPathEvaluator
    reporter: IReporter
    entry_writers: Sequence[IArchiveEntryWriter]
    compiled_rules: list[DIgnoreRule]
    rescued_files: list[tuple[str, str]]
    excluded_files: list[str]


class IPackager(DPackager, metaclass=MPackager):
    """Nominal interface for traversing sources and producing ZIP archives."""

    def collect_members(self) -> Iterator[tuple[Path, str]]:
        raise NotImplementedError

    def write_archive(self, path: Path, entries: Sequence[tuple[Path, str]]) -> None:
        raise NotImplementedError

    def package(self) -> Path:
        raise NotImplementedError
