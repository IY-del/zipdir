"""Non-greedy directory pruning and exclusion tracking via progressive inheritance over base.ZipPackager."""

from pathlib import Path, PurePosixPath

from zipdir.packager.base import ZipPackager as BaseZipPackager


class ZipPackager(BaseZipPackager):
    """Extends base ZipPackager with non-greedy directory pruning and excluded path recording."""

    def _filter_dirnames(self, dirpath: Path, rel_dir: Path, dirnames: list[str]) -> None:
        super()._filter_dirnames(dirpath, rel_dir, dirnames)
        kept: list[str] = []
        for d in dirnames:
            d_rel = rel_dir / d if rel_dir != Path(".") else Path(d)
            d_posix = PurePosixPath(d_rel.as_posix())
            if self.evaluator.should_prune(d_posix):
                entry_str = f"{d_posix.as_posix()}/"
                if (
                    d_posix.as_posix() not in self.excluded_files
                    and entry_str not in self.excluded_files
                ):
                    self.excluded_files.append(entry_str)
            else:
                kept.append(d)
        dirnames[:] = kept

    def _evaluate_file(
        self, file_posix: PurePosixPath, prefix: PurePosixPath
    ) -> tuple[str, PurePosixPath, bool] | None:
        evaluated = super()._evaluate_file(file_posix, prefix)
        if evaluated is None and file_posix.as_posix() not in self.excluded_files:
            self.excluded_files.append(file_posix.as_posix())
        return evaluated
