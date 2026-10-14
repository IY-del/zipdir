"""Preset definition, loading, C3 linearization, and 4-tier cascade resolution."""

import os
import sys
from collections.abc import Callable, Mapping, Sequence
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
    """Manages preset discovery, C3 inheritance linearization, and 4-tier .zipignore rule cascading."""

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
        """Discover and load presets from configuration directories, resolving inheritance via C3 linearization."""
        raw_presets = self._discover_raw_presets()
        presets: dict[str, PresetModel] = {}

        for name, raw_model in raw_presets.items():
            try:
                desc, rules, src = self._resolve_preset_chain(name, raw_presets)
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

    def linearize_presets(
        self,
        name: str,
        raw_presets: Mapping[str, PresetModel],
    ) -> list[str]:
        """Return the base-to-derived rule application order for `name` using C3 linearization.

        In `.zipignore`, `# inherit: p1, p2` declares `p1` as base and `p2` as override.
        In MRO (most-specific first) terms, direct parents are ordered `[p2, p1]`, and the
        resulting C3 MRO is reversed to yield the base-to-derived evaluation sequence.
        """

        def get_mro_parents(node: str) -> list[str]:
            if node not in raw_presets:
                raise ValueError(f"Preset '{node}' not found in configuration directories")
            return list(reversed(raw_presets[node].extends))

        mro = self._compute_c3_mro(name, get_mro_parents, [])
        return list(reversed(mro))

    def _compute_c3_mro(
        self,
        node: str,
        get_mro_parents: Callable[[str], list[str]],
        visiting: list[str],
    ) -> list[str]:
        """Compute C3 superclass linearization MRO (most-specific to least-specific)."""
        if node in visiting:
            cycle_path = " -> ".join([*visiting, node])
            raise ValueError(f"Circular dependency in preset inheritance: {cycle_path}")

        next_visiting = [*visiting, node]
        parents = get_mro_parents(node)
        if not parents:
            return [node]

        parent_mros = [self._compute_c3_mro(p, get_mro_parents, next_visiting) for p in parents]
        merged = self._c3_merge([*parent_mros, list(parents)])
        return [node, *merged]

    def _c3_merge(self, sequences: list[list[str]]) -> list[str]:
        """Standard C3 merge algorithm with warning and provisional fallback on order conflicts."""
        result: list[str] = []
        active = [list(seq) for seq in sequences if seq]

        while active:
            candidate: str | None = None
            for seq in active:
                head = seq[0]
                if all(head not in other[1:] for other in active):
                    candidate = head
                    break

            if candidate is None:
                candidate = active[0][0]
                print(
                    f"zipdir: warning: C3 linearization conflict in preset inheritance {active}; "
                    f"provisionally selecting '{candidate}'",
                    file=sys.stderr,
                )

            result.append(candidate)
            next_active: list[list[str]] = []
            for seq in active:
                rem = [item for item in seq if item != candidate]
                if rem:
                    next_active.append(rem)
            active = next_active

        return result

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
    ) -> tuple[str, list[str], Path | None]:
        order = self.linearize_presets(name, raw_presets)
        merged_rules: list[str] = []
        inherited_desc = raw_presets[name].description

        for node_name in order:
            node_model = raw_presets[node_name]
            merged_rules.extend(node_model.rules)
            if not inherited_desc and node_model.description:
                inherited_desc = node_model.description

        squeezed = self.interpreter.squeeze(merged_rules)
        final_rules = [r if isinstance(r, str) else r.rule for r in squeezed]
        return inherited_desc, final_rules, raw_presets[name].source_path

    def _resolve_extended_rules(
        self,
        extends: Sequence[str],
        base_dir: Path,
        loaded_presets: Mapping[str, PresetModel],
        root_file: Path | None = None,
    ) -> list[str]:
        """Resolve `# inherit:` / `# extends:` / `# include:` targets using C3 linearization."""
        raw_presets = self._discover_raw_presets()
        for k, v in loaded_presets.items():
            if k not in raw_presets:
                raw_presets[k] = v

        models_by_key: dict[str, PresetModel] = dict(raw_presets)
        base_dirs_by_key: dict[str, Path] = {
            k: (v.source_path.parent if v.source_path is not None else base_dir)
            for k, v in raw_presets.items()
        }

        root_key = f"__file__:{root_file.resolve()}" if root_file is not None else "__root__"
        models_by_key[root_key] = PresetModel(name=root_key, extends=list(extends), rules=[])
        base_dirs_by_key[root_key] = base_dir

        def resolve_parent_key(parent_ref: str, current_dir: Path) -> str | None:
            if parent_ref in models_by_key:
                return parent_ref
            expanded = Path(parent_ref).expanduser()
            candidate = expanded if expanded.is_absolute() else (current_dir / expanded)
            if candidate.is_file():
                canon = candidate.resolve()
                file_key = f"__file__:{canon}"
                if file_key not in models_by_key:
                    models_by_key[file_key] = self.parse_file(canon)
                    base_dirs_by_key[file_key] = canon.parent
                return file_key
            print(
                f"zipdir: warning: preset '{parent_ref}' declared in .zipignore not found",
                file=sys.stderr,
            )
            return None

        def get_mro_parents(node_key: str) -> list[str]:
            model = models_by_key[node_key]
            curr_dir = base_dirs_by_key.get(node_key, base_dir)
            resolved_parents: list[str] = []
            for p_ref in model.extends:
                p_key = resolve_parent_key(p_ref, curr_dir)
                if p_key is not None and p_key not in resolved_parents:
                    resolved_parents.append(p_key)
            return list(reversed(resolved_parents))

        mro = self._compute_c3_mro(root_key, get_mro_parents, [])
        eval_order = [k for k in reversed(mro) if k != root_key]

        merged_rules: list[str] = []
        for k in eval_order:
            merged_rules.extend(models_by_key[k].rules)
        squeezed = self.interpreter.squeeze(merged_rules)
        return [r if isinstance(r, str) else r.rule for r in squeezed]

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
                            preset_path,
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
                        local_zipignore if local_zipignore.is_file() else None,
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
                    local_zipignore,
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
                    sub_file,
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
