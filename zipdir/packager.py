"""Core packaging engine (direct-to-archive writer with non-greedy pruning)."""

import os
import stat
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath

from zipdir.evaluator import PathEvaluator
from zipdir.models import IgnoreRule, PackagerConfig, RuleKind
from zipdir.ui import ConsoleReporter


class ZipPackager:
    """Traverses source directory using PathEvaluator and writes ZIP archives atomically."""

    config: PackagerConfig
    evaluator: PathEvaluator
    reporter: ConsoleReporter
    compiled_rules: list[IgnoreRule]
    rescued_files: list[tuple[str, str]]
    excluded_files: list[str]

    def __init__(
        self,
        config: PackagerConfig,
        evaluator: PathEvaluator | None = None,
        reporter: ConsoleReporter | None = None,
    ) -> None:
        self.config = config
        self.evaluator = evaluator or PathEvaluator(config.rules)
        self.reporter = reporter or ConsoleReporter()
        self.compiled_rules = list(self.evaluator.rules)
        self.rescued_files = []
        self.excluded_files = []

    def _is_self_archive(self, file_path: Path) -> bool:
        """Prevent packaging the target output archive or temporary staging files into itself."""
        if file_path.name.startswith(".zipdir_") and file_path.name.endswith(".zip"):
            return True
        resolved = file_path.resolve()
        output_resolved = self.config.output.resolve()
        if resolved == output_resolved:
            return True
        # Also skip the base <name>.zip if output fell back to <name>_<timestamp>.zip in the same dir
        if resolved.parent == output_resolved.parent and resolved.name == f"{self.config.name}.zip":
            if output_resolved.name.startswith(
                f"{self.config.name}_"
            ) and output_resolved.name.endswith(".zip"):
                return True
        return False

    def collect_members(self) -> Iterator[tuple[Path, str]]:
        """Traverse source directory and yield (filesystem_path, arcname) pairs."""
        prefix = PurePosixPath() if self.config.flat else PurePosixPath(self.config.name)
        if not self.config.flat:
            yield self.config.source, prefix.as_posix() + "/"

        for dirpath, dirnames, filenames in self.config.source.walk(follow_symlinks=False):
            rel_dir = dirpath.relative_to(self.config.source)

            pruned_dirs: list[str] = []
            for d in dirnames:
                full_d = dirpath / d
                try:
                    mode = os.lstat(full_d).st_mode
                    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                        pruned_dirs.append(d)
                        continue
                except OSError:
                    pruned_dirs.append(d)
                    continue

                d_rel = rel_dir / d if rel_dir != Path(".") else Path(d)
                d_posix = PurePosixPath(d_rel.as_posix())
                if self.evaluator.should_prune(d_posix):
                    pruned_dirs.append(d)
                    entry_str = d_posix.as_posix() + "/"
                    if (
                        d_posix.as_posix() not in self.excluded_files
                        and entry_str not in self.excluded_files
                    ):
                        self.excluded_files.append(entry_str)

            for d in pruned_dirs:
                dirnames.remove(d)

            dirnames.sort()
            filenames.sort()

            for fname in filenames:
                file_path = dirpath / fname
                if self._is_self_archive(file_path):
                    continue
                try:
                    mode = os.lstat(file_path).st_mode
                    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                        continue
                except OSError:
                    continue

                file_rel = rel_dir / fname if rel_dir != Path(".") else Path(fname)
                file_posix = PurePosixPath(file_rel.as_posix())

                result = self.evaluator.evaluate(file_posix, is_dir=False)
                if result.is_excluded:
                    if file_posix.as_posix() not in self.excluded_files:
                        self.excluded_files.append(file_posix.as_posix())
                    continue

                if result.arc_path is None:
                    continue

                if result.matched_rule is not None and result.matched_rule.kind == RuleKind.RESCUE:
                    self.rescued_files.append((file_posix.as_posix(), result.arc_path.as_posix()))

                full_arcname = (prefix / result.arc_path).as_posix()
                yield file_path, full_arcname

    def write_archive(self, path: Path, entries: Sequence[tuple[Path, str]]) -> None:
        """Write member files into the target ZIP archive directly."""
        method = zipfile.ZIP_STORED if self.config.compression == 0 else zipfile.ZIP_DEFLATED
        with zipfile.ZipFile(
            path, "w", compression=method, compresslevel=self.config.compression
        ) as archive:
            for item, arcname in entries:
                if item == self.config.source:
                    info = zipfile.ZipInfo(arcname)
                    archive.writestr(info, "")
                    continue
                if item.is_symlink():
                    info = zipfile.ZipInfo(arcname)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, item.readlink().as_posix())
                else:
                    archive.write(item, arcname)

    def package(self) -> Path:
        """Evaluate paths, handle dry-run, or atomically write ZIP archive."""
        output = self.config.output
        if not self.config.dry_run:
            if not self.config.force and (output.exists() or output.is_symlink()):
                raise FileExistsError(
                    f"Output already exists (use -f/--force to overwrite): {output}"
                )
            if not output.parent.is_dir():
                raise FileNotFoundError(f"Output parent directory does not exist: {output.parent}")

        entries = list(self.collect_members())

        if self.config.dry_run:
            self.reporter.print_dry_run(
                self.config, entries, self.rescued_files, self.excluded_files
            )
            return output

        fd, temp_file_str = tempfile.mkstemp(prefix=".zipdir_", suffix=".zip", dir=output.parent)
        os.close(fd)
        temp_path = Path(temp_file_str)
        try:
            self.write_archive(temp_path, entries)
            if self.config.force and (output.exists() or output.is_symlink()):
                output.unlink()
            output.hardlink_to(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.reporter.print_summary(
            self.config, output, entries, self.rescued_files, self.excluded_files
        )
        return output
