"""Atomic and dry-run packager via progressive inheritance over phagocytic.ZipPackager."""

import os
import tempfile
from pathlib import Path

from zipdir.packager.phagocytic import ZipPackager as PhagocyticZipPackager


class ZipPackager(PhagocyticZipPackager):
    """Extends PhagocyticZipPackager with pre-flight checks, dry-run preview, and atomic hardlink write."""

    def package(self) -> Path:
        """Evaluate paths, handle dry-run, or atomically write ZIP archive."""
        output = self.config.output
        match self.config.dry_run:
            case False:
                self._validate_output_target(output)
            case True:
                pass

        entries = list(self.collect_members())
        match self.config.dry_run:
            case True:
                self.reporter.print_dry_run(
                    self.config, entries, self.rescued_files, self.excluded_files
                )
                return output
            case False:
                self._write_atomic_archive(output, entries)
                self.reporter.print_summary(
                    self.config, output, entries, self.rescued_files, self.excluded_files
                )
                return output

    def _validate_output_target(self, output: Path) -> None:
        match not self.config.force and (output.exists() or output.is_symlink()):
            case True:
                raise FileExistsError(
                    f"Output already exists (use -f/--force to overwrite): {output}"
                )
            case False:
                match not output.parent.is_dir():
                    case True:
                        raise FileNotFoundError(
                            f"Output parent directory does not exist: {output.parent}"
                        )
                    case False:
                        pass

    def _write_atomic_archive(self, output: Path, entries: list[tuple[Path, str]]) -> None:
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
