"""Subdirectory .zipignore cascade via progressive inheritance over local.PresetCatalog."""

from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from zipdir.models import PresetModel, ScopedRule
from zipdir.presets.local import PresetCatalog as LocalPresetCatalog


class PresetCatalog(LocalPresetCatalog):
    """Extends LocalPresetCatalog with subdirectory .zipignore discovery (Tier 3)."""

    def discover_sub_zipignores(self, source: Path) -> list[tuple[PurePosixPath, Path]]:
        """Discover all .zipignore files in subdirectories under source, sorted by depth."""
        found: list[tuple[PurePosixPath, Path]] = []
        for dirpath, dirnames, filenames in source.walk(follow_symlinks=False):
            dirnames[:] = [d for d in dirnames if d not in (".git", ".svn", ".hg")]
            if dirpath == source:
                continue
            if ".zipignore" in filenames:
                rel_dir = PurePosixPath(dirpath.relative_to(source).as_posix())
                found.append((rel_dir, dirpath / ".zipignore"))
        found.sort(key=lambda item: (len(item[0].parts), item[0].as_posix()))
        return found

    def _collect_tier3_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, PresetModel],
    ) -> list[ScopedRule]:
        tier3_rules: list[ScopedRule] = []
        for rel_dir, sub_file in self.discover_sub_zipignores(source):
            sub_model = self.parse_file(sub_file)
            match sub_model.extends:
                case list() as ext if ext:
                    inherited = self._resolve_extended_rules(
                        ext,
                        sub_file.parent,
                        loaded_presets,
                        sub_file,
                    )
                    tier3_rules.extend(ScopedRule(scope=rel_dir, rule=r) for r in inherited)
                case _:
                    pass
            tier3_rules.extend(ScopedRule(scope=rel_dir, rule=r) for r in sub_model.rules)
        return tier3_rules
