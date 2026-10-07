"""Core packaging engine (direct-to-archive writer with pruning optimization)."""

import os
import stat
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path, PurePosixPath

from zipdir.evaluator import evaluate_path
from zipdir.interpreter import compile_rule
from zipdir.models import PackagerConfig, RuleKind, ScopedRule
from zipdir.ui import (
    color_bold,
    color_cyan,
    color_dim,
    color_success,
    color_yellow,
)


class ZipPackager:
    """Processes rules and generates archives directly without unnecessary staging."""

    def __init__(self, config: PackagerConfig) -> None:
        self.config = config
        self.compiled_rules = []
        for item in config.rules:
            if isinstance(item, ScopedRule):
                if (r := compile_rule(item.rule, scope=item.scope)) is not None:
                    self.compiled_rules.append(r)
            elif isinstance(item, str):
                if (r := compile_rule(item)) is not None:
                    self.compiled_rules.append(r)
        self.rescued_files: list[tuple[str, str]] = []
        self.excluded_files: list[str] = []

    def _should_prune_directory(self, rel_dir: PurePosixPath) -> bool:
        """Check if an excluded directory has any active rescue rules that could target its contents.
        If all rescue rules have been eaten by REDELETE or parent EXCLUDE, prune immediately!
        """
        posix_str = rel_dir.as_posix()
        is_excluded, _, _ = evaluate_path(rel_dir, is_dir=True, rules=self.compiled_rules)
        if not is_excluded:
            return False

        for r in self.compiled_rules:
            if r.kind != RuleKind.RESCUE:
                continue
            if r.scope != PurePosixPath():
                # If rule is scoped inside rel_dir, it targets contents inside rel_dir
                if r.scope == rel_dir or r.scope.is_relative_to(rel_dir):
                    return False
                # If rel_dir is inside r.scope, pattern might match inside rel_dir
                if not rel_dir.is_relative_to(r.scope):
                    continue
            clean_pat = r.pattern.lstrip("/")
            if r.scope != PurePosixPath():
                full_pat = (r.scope / clean_pat).as_posix()
            else:
                full_pat = clean_pat
            if full_pat.startswith(posix_str) or posix_str.startswith(full_pat.split("*")[0]):
                return False

        return True

    def collect_members(self) -> Iterator[tuple[Path, str]]:
        """Traverse source directory and yield (filesystem_path, arcname) pairs."""
        prefix = PurePosixPath() if self.config.flat else PurePosixPath(self.config.name)
        if not self.config.flat:
            yield self.config.source, prefix.as_posix() + "/"

        for dirpath, dirnames, filenames in self.config.source.walk(follow_symlinks=False):
            rel_dir = dirpath.relative_to(self.config.source)

            # Prune excluded directories that have no active rescue rules
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
                if self._should_prune_directory(d_posix):
                    pruned_dirs.append(d)
                    if d_posix.as_posix() not in self.excluded_files:
                        self.excluded_files.append(d_posix.as_posix() + "/")

            for d in pruned_dirs:
                dirnames.remove(d)

            dirnames.sort()
            filenames.sort()

            for fname in filenames:
                file_path = dirpath / fname
                try:
                    mode = os.lstat(file_path).st_mode
                    if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                        continue
                except OSError:
                    continue

                file_rel = rel_dir / fname if rel_dir != Path(".") else Path(fname)
                file_posix = PurePosixPath(file_rel.as_posix())

                is_exc, arc_rel, matched_rule = evaluate_path(
                    file_posix, is_dir=False, rules=self.compiled_rules
                )
                if is_exc:
                    if file_posix.as_posix() not in self.excluded_files:
                        self.excluded_files.append(file_posix.as_posix())
                    continue

                if arc_rel is None:
                    continue

                if matched_rule is not None and matched_rule.kind == RuleKind.RESCUE:
                    self.rescued_files.append((file_posix.as_posix(), arc_rel.as_posix()))

                full_arcname = (prefix / arc_rel).as_posix()
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
            if output.is_relative_to(self.config.source):
                raise ValueError("Output must be outside the source directory")

        entries = list(self.collect_members())

        if self.config.dry_run:
            self._print_dry_run(entries)
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

        self._print_summary(output, entries)
        return output

    def _print_dry_run(self, entries: Sequence[tuple[Path, str]]) -> None:
        print(
            f"\n{color_yellow('[DRY RUN]')} Resulting archive structure for {color_bold(self.config.output.name)}:"
        )
        print(f"  • Source:   {self.config.source}")
        print(f"  • Preset:   {self.config.preset_name}")
        print(f"  • Rules:    {len(self.config.rules)} rules\n")
        if self.rescued_files:
            print(color_cyan("Rescued / Remapped files (!):"))
            for src, dst in self.rescued_files:
                print(f"  ↑ {src} -> {dst}")
        if self.excluded_files:
            print(color_yellow("Excluded paths:"))
            for ex in self.excluded_files:
                print(f"  ✕ {ex}")
        print(color_bold("Archive members:"))
        for _, arcname in entries:
            print(f"  + {arcname}")

    def _print_summary(self, output: Path, entries: Sequence[tuple[Path, str]]) -> None:
        file_count = sum(1 for item, arcname in entries if not arcname.endswith("/"))
        dir_count = sum(1 for item, arcname in entries if arcname.endswith("/"))
        size_str = self._format_size(output.stat().st_size)

        print(
            f"{color_success('✔')} Created archive: {color_bold(output.name)} {color_dim(f'({size_str})')}"
        )
        print(f"  {color_dim('Path:')}     {color_cyan(str(output))}")
        print(
            f"  {color_dim('Preset:')}   {self.config.preset_name} ({len(self.config.rules)} rules)"
        )
        print(f"  {color_dim('Members:')}  {file_count} files, {dir_count} directories")

        if self.config.verbose:
            if self.rescued_files:
                print(f"\n{color_cyan('Rescued / Remapped files (!):')}")
                for src, dst in self.rescued_files:
                    print(f"  ↑ {src} -> {dst}")
            if self.excluded_files:
                print(f"{color_yellow('Excluded paths:')}")
                for ex in self.excluded_files:
                    print(f"  ✕ {ex}")

    @staticmethod
    def _format_size(num_bytes: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if num_bytes < 1024.0:
                return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
            num_bytes /= 1024.0
        return f"{num_bytes:.1f} TB"
