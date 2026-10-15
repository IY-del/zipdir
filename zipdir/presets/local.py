"""Root .zipignore and custom file preset resolution via progressive inheritance over linearized.PresetCatalog."""

from collections.abc import Mapping
from pathlib import Path

from zipdir.interfaces.models import DPreset
from zipdir.models import PresetModel, ScopedRule
from zipdir.presets.linearized import PresetCatalog as LinearizedPresetCatalog


class PresetCatalog(LinearizedPresetCatalog):
    """Extends LinearizedPresetCatalog with custom preset file and Tier-2 root .zipignore resolution."""

    def _collect_tier1_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, DPreset],
        preset: str | None,
        local_model: PresetModel | None,
        effective_name: str,
    ) -> tuple[list[str], str]:
        if preset is not None:
            preset_path = Path(preset).expanduser()
            if preset not in loaded_presets and preset_path.is_file():
                custom_model = self.parse_file(preset_path)
                extended = self._resolve_extended_rules(
                    custom_model.extends,
                    preset_path.parent,
                    loaded_presets,
                    preset_path,
                )
                return [*extended, *custom_model.rules], custom_model.name or preset_path.name
        elif local_model is not None and local_model.extends:
            extended = self._resolve_extended_rules(
                local_model.extends,
                source,
                loaded_presets,
                local_model.source_path,
            )
            return extended, effective_name
        return super()._collect_tier1_rules(
            source, loaded_presets, preset, local_model, effective_name
        )

    def _collect_tier2_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, DPreset],
        preset: str | None,
        local_model: PresetModel | None,
    ) -> list[ScopedRule]:
        if local_model is None:
            return []
        tier2_raw: list[str] = []
        if preset is not None and local_model.extends:
            tier2_raw.extend(
                self._resolve_extended_rules(
                    local_model.extends,
                    source,
                    loaded_presets,
                    local_model.source_path,
                )
            )
        tier2_raw.extend(local_model.rules)
        return [ScopedRule(rule=r) for r in tier2_raw]
