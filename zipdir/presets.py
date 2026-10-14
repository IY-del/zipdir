"""Preset definition, loading, and 4-tier cascade resolution."""

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from zipdir.models import PresetModel, ScopedRule
from zipdir.squeezer import RuleInterpreter

DEFAULT_PRESET_DIRS: list[Path] = [
    Path(__file__).resolve().parent.parent / "presets",
    Path(__file__).resolve().parent / "presets",
    Path.home() / ".config" / "zipdir" / "presets",
    Path.home() / ".dcfg" / "config" / "zipdir" / "presets",
]


class PresetCatalog:
    """Manages preset discovery, inheritance resolution, and 4-tier .zipignore rule cascading."""

    preset_dirs: list[Path]
    interpreter: RuleInterpreter

    def __init__(
        self,
        preset_dirs: Sequence[Path] | None = None,
        interpreter: RuleInterpreter | None = None,
    ) -> None:
        dirs = list(preset_dirs) if preset_dirs is not None else list(DEFAULT_PRESET_DIRS)
        if "ZIPDIR_PRESETS_DIR" in os.environ:
            dirs.insert(0, Path(os.environ["ZIPDIR_PRESETS_DIR"]))
        self.preset_dirs = dirs
        self.interpreter = interpreter or RuleInterpreter()

    def parse_file(self, file: Path) -> PresetModel:
        """Parse a .zipignore preset file extracting description, inherit/extends, and rule lines."""
        content = file.read_text(encoding="utf-8")
        description = ""
        extends: list[str] = []
        rules: list[str] = []

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                lower = stripped.lower()
                if any(k in lower for k in ("inherit:", "extends:", "include:")):
                    val = stripped.split(":", 1)[1]
                    for p in val.split(","):
                        p_clean = p.strip()
                        if p_clean and p_clean not in extends:
                            extends.append(p_clean)
                elif "description:" in lower:
                    description = stripped.split(":", 1)[1].strip()
                continue
            rules.append(stripped)

        stem = self._extract_preset_stem(file)
        return PresetModel(
            name=stem,
            description=description,
            rules=rules,
            extends=extends,
            source_path=file,
        )

    def load_all(self) -> dict[str, PresetModel]:
        """Discover and load presets from configuration directories, resolving inheritance."""
        raw_presets = self._discover_raw_presets()
        presets: dict[str, PresetModel] = {}

        for name, raw_model in raw_presets.items():
            try:
                desc, rules, src = self._resolve_preset_chain(name, raw_presets, [])
                presets[name] = PresetModel(
                    name=name,
                    description=desc,
                    rules=rules,
                    extends=raw_model.extends,
                    source_path=src,
                )
            except Exception as e:
                print(
                    f"zipdir: warning: failed to resolve preset '{name}': {e}",
                    file=sys.stderr,
                )

        return presets

    def _extract_preset_stem(self, file: Path) -> str:
        stem = file.name
        if stem.endswith(".zipignore"):
            return stem.removesuffix(".zipignore")
        if stem.endswith((".yaml", ".yml")):
            return file.stem
        return stem

    def _discover_raw_presets(self) -> dict[str, PresetModel]:
        raw_presets: dict[str, PresetModel] = {}
        for directory in self.preset_dirs:
            if not directory.is_dir():
                continue
            found_files = (
                sorted(directory.glob("*.zipignore"))
                + sorted(directory.glob("*.yaml"))
                + sorted(directory.glob("*.yml"))
            )
            for file in found_files:
                stem = self._extract_preset_stem(file)
                if stem not in raw_presets:
                    try:
                        raw_presets[stem] = self.parse_file(file)
                    except Exception as e:
                        print(
                            f"zipdir: warning: failed to parse preset '{file}': {e}",
                            file=sys.stderr,
                        )
        return raw_presets

    def _resolve_preset_chain(
        self,
        name: str,
        raw_presets: Mapping[str, PresetModel],
        visited: list[str],
    ) -> tuple[str, list[str], Path | None]:
        if name in visited:
            raise ValueError(
                f"Circular dependency in preset inheritance: {' -> '.join(visited)} -> {name}"
            )
        visited.append(name)

        if name not in raw_presets:
            raise ValueError(f"Preset '{name}' not found in configuration directories")

        model = raw_presets[name]
        merged_rules: list[str] = []
        inherited_desc = model.description
        for parent in model.extends:
            p_desc, p_rules, _ = self._resolve_preset_chain(parent, raw_presets, visited.copy())
            merged_rules.extend(p_rules)
            if not inherited_desc:
                inherited_desc = p_desc

        merged_rules.extend(model.rules)
        squeezed = self.interpreter.squeeze(merged_rules)
        final_rules = [r if isinstance(r, str) else r.rule for r in squeezed]
        return inherited_desc, final_rules, model.source_path

    def _resolve_extended_rules(
        self,
        extends: Sequence[str],
        base_dir: Path,
        loaded_presets: Mapping[str, PresetModel],
        visited_files: set[Path] | None = None,
    ) -> list[str]:
        """Resolve `# inherit:` / `# extends:` / `# include:` targets (presets or relative ignore files)."""
        seen_files = set(visited_files) if visited_files is not None else set()
        resolved_rules: list[str] = []

        for target in extends:
            if target in loaded_presets:
                for r in loaded_presets[target].rules:
                    if r not in resolved_rules:
                        resolved_rules.append(r)
                continue

            expanded = Path(target).expanduser()
            candidate = expanded if expanded.is_absolute() else (base_dir / expanded)
            if candidate.is_file():
                canon = candidate.resolve()
                if canon in seen_files:
                    raise ValueError(f"Circular dependency in ignore file inheritance: {candidate}")
                next_seen = seen_files | {canon}
                included_model = self.parse_file(canon)
                if included_model.extends:
                    parent_rules = self._resolve_extended_rules(
                        included_model.extends,
                        canon.parent,
                        loaded_presets,
                        next_seen,
                    )
                    for r in parent_rules:
                        if r not in resolved_rules:
                            resolved_rules.append(r)
                for r in included_model.rules:
                    if r not in resolved_rules:
                        resolved_rules.append(r)
                continue

            print(
                f"zipdir: warning: preset '{target}' declared in .zipignore not found",
                file=sys.stderr,
            )

        return resolved_rules

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

    def resolve_cascade(
        self,
        source: Path,
        presets: dict[str, PresetModel] | None = None,
        *,
        preset: str | None = None,
        cli_rules: Sequence[str] = (),
        no_default_rules: bool = False,
    ) -> tuple[str, list[str | ScopedRule]]:
        """Build and squeeze the 4-tier rule cascade (Preset -> Root -> Subdir -> CLI)."""
        loaded_presets = presets if presets is not None else self.load_all()

        local_zipignore = source / ".zipignore"
        local_rules: list[str] = []
        local_extends: list[str] = []
        if local_zipignore.is_file():
            local_model = self.parse_file(local_zipignore)
            local_rules = local_model.rules
            local_extends = local_model.extends

        effective_preset_name = (
            preset
            if preset is not None
            else (", ".join(local_extends) if local_extends else "clean")
        )

        base_rules: list[str] = []
        if not no_default_rules:
            if preset is not None:
                preset_path = Path(preset).expanduser()
                if preset not in loaded_presets and preset_path.is_file():
                    custom_model = self.parse_file(preset_path)
                    base_rules.extend(
                        self._resolve_extended_rules(
                            custom_model.extends,
                            preset_path.parent,
                            loaded_presets,
                            {preset_path.resolve()},
                        )
                    )
                    base_rules.extend(custom_model.rules)
                    effective_preset_name = custom_model.name or preset_path.name
                elif preset in loaded_presets:
                    base_rules.extend(loaded_presets[preset].rules)
                else:
                    available = ", ".join(loaded_presets.keys())
                    raise ValueError(f"Unknown preset '{preset}'. Available: {available}")
            elif local_extends:
                base_rules.extend(
                    self._resolve_extended_rules(
                        local_extends,
                        source,
                        loaded_presets,
                        {local_zipignore.resolve()} if local_zipignore.is_file() else None,
                    )
                )
            elif "clean" in loaded_presets:
                base_rules.extend(loaded_presets["clean"].rules)

        tier1_rules = [ScopedRule(rule=p) for p in base_rules]

        tier2_raw: list[str] = []
        if preset is not None and local_extends:
            tier2_raw.extend(
                self._resolve_extended_rules(
                    local_extends,
                    source,
                    loaded_presets,
                    {local_zipignore.resolve()},
                )
            )
        tier2_raw.extend(local_rules)
        tier2_rules = [ScopedRule(rule=r) for r in tier2_raw]

        tier3_rules: list[ScopedRule] = []
        for rel_dir, sub_file in self.discover_sub_zipignores(source):
            sub_model = self.parse_file(sub_file)
            if sub_model.extends:
                inherited_sub_rules = self._resolve_extended_rules(
                    sub_model.extends,
                    sub_file.parent,
                    loaded_presets,
                    {sub_file.resolve()},
                )
                for r in inherited_sub_rules:
                    tier3_rules.append(ScopedRule(scope=rel_dir, rule=r))
            for r in sub_model.rules:
                tier3_rules.append(ScopedRule(scope=rel_dir, rule=r))

        tier4_rules = [ScopedRule(rule=r) for r in cli_rules]

        combined_raw = tier1_rules + tier2_rules + tier3_rules + tier4_rules
        return effective_preset_name, self.interpreter.squeeze(combined_raw)


def load_raw_zipignore_preset(file: Path) -> PresetModel:
    """Parse a .zipignore preset file extracting description, inherit/extends, and rule lines."""
    return PresetCatalog().parse_file(file)


def load_presets(preset_dirs: Sequence[Path] | None = None) -> dict[str, PresetModel]:
    """Discover and load presets from configuration directories."""
    return PresetCatalog(preset_dirs=preset_dirs).load_all()


def discover_sub_zipignores(source: Path) -> list[tuple[PurePosixPath, Path]]:
    """Discover all .zipignore files in subdirectories under source, sorted by depth."""
    return PresetCatalog().discover_sub_zipignores(source)
