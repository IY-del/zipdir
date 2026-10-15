"""Member-level arcname phagocytosis and rescued tracking via progressive inheritance over pruned.ZipPackager."""

from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from zipdir.packager.pruned import ZipPackager as PrunedZipPackager


class ZipPackager(PrunedZipPackager):
    """Extends PrunedZipPackager with member-level arcname collision replacement and rescued tracking."""

    _seen_arcnames: dict[str, int]
    _rescued_by_arcname: dict[str, tuple[str, str]]

    def _init_staged_entries(self, prefix: PurePosixPath) -> list[tuple[Path, str]]:
        staged = super()._init_staged_entries(prefix)
        self._seen_arcnames = {arcname: idx for idx, (_, arcname) in enumerate(staged)}
        self._rescued_by_arcname = {}
        return staged

    def _stage_member(
        self,
        staged: list[tuple[Path, str]],
        file_path: Path,
        full_arcname: str,
        file_posix: PurePosixPath,
        arc_path: PurePosixPath,
        is_rescued: bool,
    ) -> None:
        if full_arcname in self._seen_arcnames:
            staged[self._seen_arcnames[full_arcname]] = (file_path, full_arcname)
        else:
            self._seen_arcnames[full_arcname] = len(staged)
            staged.append((file_path, full_arcname))

        if is_rescued:
            self._rescued_by_arcname[full_arcname] = (
                file_posix.as_posix(),
                arc_path.as_posix(),
            )
        else:
            self._rescued_by_arcname.pop(full_arcname, None)

    def _finalize_collection(self, staged: Sequence[tuple[Path, str]]) -> None:
        self.rescued_files = [
            self._rescued_by_arcname[arcname]
            for _, arcname in staged
            if arcname in self._rescued_by_arcname
        ]
