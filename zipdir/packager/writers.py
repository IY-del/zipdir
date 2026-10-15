"""Concrete archive entry writer strategies."""

import stat
import zipfile
from pathlib import Path

from zipdir.interfaces.packager import IArchiveEntryWriter


class RootDirArchiveWriter(IArchiveEntryWriter):
    """Concrete Strategy for writing the enclosing top-level root directory entry."""

    def matches(self, item: Path, source: Path) -> bool:
        return item == source

    def write(self, archive: zipfile.ZipFile, item: Path, arcname: str) -> None:
        info = zipfile.ZipInfo(arcname)
        archive.writestr(info, "")


class SymlinkArchiveWriter(IArchiveEntryWriter):
    """Concrete Strategy for preserving symbolic links inside the ZIP archive."""

    def matches(self, item: Path, source: Path) -> bool:
        return item != source and item.is_symlink()

    def write(self, archive: zipfile.ZipFile, item: Path, arcname: str) -> None:
        info = zipfile.ZipInfo(arcname)
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, item.readlink().as_posix())


class RegularFileArchiveWriter(IArchiveEntryWriter):
    """Concrete fallback Strategy for writing regular files into the ZIP archive."""

    def matches(self, item: Path, source: Path) -> bool:
        return True

    def write(self, archive: zipfile.ZipFile, item: Path, arcname: str) -> None:
        archive.write(item, arcname)


DEFAULT_ENTRY_WRITERS: tuple[IArchiveEntryWriter, ...] = (
    RootDirArchiveWriter(),
    SymlinkArchiveWriter(),
    RegularFileArchiveWriter(),
)
