"""C3 linearization preset catalog via progressive inheritance over base.PresetCatalog."""

import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from zipdir.interfaces.models import DPreset
from zipdir.models import PresetModel
from zipdir.presets.base import (
    PresetCatalog as BasePresetCatalog,
)
from zipdir.presets.base import (
    _as_preset_model,
)


class PresetCatalog(BasePresetCatalog):
    """Extends base PresetCatalog with C3 superclass linearization for multi-inheritance."""

    def load_all(self) -> dict[str, PresetModel]:
        """Discover and load presets from configuration directories, resolving inheritance via C3."""
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
        raw_presets: Mapping[str, DPreset],
    ) -> list[str]:
        """Return the base-to-derived rule application order for `name` using C3 linearization."""

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
            candidate = self._select_c3_head(active)
            result.append(candidate)
            active = [rem for seq in active if (rem := [item for item in seq if item != candidate])]

        return result

    def _select_c3_head(self, active: Sequence[Sequence[str]]) -> str:
        for seq in active:
            head = seq[0]
            if all(head not in other[1:] for other in active):
                return head
        fallback = active[0][0]
        print(
            f"zipdir: warning: C3 linearization conflict in preset inheritance {active}; "
            f"provisionally selecting '{fallback}'",
            file=sys.stderr,
        )
        return fallback

    def _resolve_preset_chain(
        self,
        name: str,
        raw_presets: Mapping[str, DPreset],
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
        loaded_presets: Mapping[str, DPreset],
        root_file: Path | None = None,
    ) -> list[str]:
        """Resolve `# inherit:` / `# extends:` / `# include:` targets using C3 linearization."""
        models_by_key, base_dirs_by_key, root_key = self._init_inheritance_graph(
            extends, base_dir, loaded_presets, root_file
        )

        def get_mro_parents(node_key: str) -> list[str]:
            model = models_by_key[node_key]
            curr_dir = base_dirs_by_key.get(node_key, base_dir)
            resolved_parents: list[str] = []
            for p_ref in model.extends:
                p_key = self._resolve_parent_key(p_ref, curr_dir, models_by_key, base_dirs_by_key)
                if p_key is not None and p_key not in resolved_parents:
                    resolved_parents.append(p_key)
            return list(reversed(resolved_parents))

        mro = self._compute_c3_mro(root_key, get_mro_parents, [])
        eval_order = [k for k in reversed(mro) if k != root_key]

        merged_rules = [rule for k in eval_order for rule in models_by_key[k].rules]
        squeezed = self.interpreter.squeeze(merged_rules)
        return [r if isinstance(r, str) else r.rule for r in squeezed]

    def _init_inheritance_graph(
        self,
        extends: Sequence[str],
        base_dir: Path,
        loaded_presets: Mapping[str, DPreset],
        root_file: Path | None,
    ) -> tuple[dict[str, PresetModel], dict[str, Path], str]:
        raw_presets: dict[str, PresetModel] = dict(self._discover_raw_presets())
        for k, v in loaded_presets.items():
            if k not in raw_presets:
                raw_presets[k] = _as_preset_model(v)

        models_by_key: dict[str, PresetModel] = dict(raw_presets)
        base_dirs_by_key: dict[str, Path] = {
            k: (v.source_path.parent if v.source_path is not None else base_dir)
            for k, v in raw_presets.items()
        }
        root_key = f"__file__:{root_file.resolve()}" if root_file is not None else "__root__"
        models_by_key[root_key] = PresetModel(name=root_key, extends=list(extends), rules=[])
        base_dirs_by_key[root_key] = base_dir
        return models_by_key, base_dirs_by_key, root_key

    def _resolve_parent_key(
        self,
        parent_ref: str,
        current_dir: Path,
        models_by_key: dict[str, PresetModel],
        base_dirs_by_key: dict[str, Path],
    ) -> str | None:
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
