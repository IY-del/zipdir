"""Interfaces for archive packaging and entry writing."""

from pathlib import Path
from zipfile import ZipFile

from zipdir.models import PackagerConfig


class IArchiveEntryWriter:
    """Strategy interface for writing filesystem entries into a ZIP archive."""

    def write(self, zf: ZipFile, fs_path: Path, arcname: str) -> None:
        raise NotImplementedError


class IPackager:
    """Interface for packaging directories into ZIP archives."""

    def package(self, config: PackagerConfig) -> tuple[Path, int]:
        raise NotImplementedError
