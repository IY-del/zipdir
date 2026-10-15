"""Root .zipignore and custom file preset resolution via progressive inheritance over linearized.PresetCatalog."""

from collections.abc import Mapping
from pathlib import Path

from zipdir.models import PresetModel, ScopedRule
from zipdir.presets.linearized import PresetCatalog as LinearizedPresetCatalog


class PresetCatalog(LinearizedPresetCatalog):
    """Extends LinearizedPresetCatalog with custom preset file and Tier-2 root .zipignore resolution."""

    def _collect_tier1_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, PresetModel],
        preset: str | None,
        local_model: PresetModel | None,
        effective_name: str,
    ) -> tuple[list[str], str]:
        match (preset, local_model):
            case (str() as p, _) if p not in loaded_presets and Path(p).expanduser().is_file():
                preset_path = Path(p).expanduser()
                custom_model = self.parse_file(preset_path)
                extended = self._resolve_extended_rules(
                    custom_model.extends,
                    preset_path.parent,
                    loaded_presets,
                    preset_path,
                )
                return [*extended, *custom_model.rules], custom_model.name or preset_path.name
            case (None, PresetModel(extends=extends, source_path=src)) if extends:
                extended = self._resolve_extended_rules(
                    extends,
                    source,
                    loaded_presets,
                    src,
                )
                return extended, effective_name
            case _:
                return super()._collect_tier1_rules(
                    source, loaded_presets, preset, local_model, effective_name
                )

    def _collect_tier2_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, PresetModel],
        preset: str | None,
        local_model: PresetModel | None,
    ) -> list[ScopedRule]:
        match local_model:
            case None:
                return []
            case PresetModel(rules=local_rules, extends=local_extends, source_path=src):
                tier2_raw: list[str] = []
                match (preset, local_extends):
                    case (str(), list() as ext) if ext:
                        tier2_raw.extend(
                            self._resolve_extended_rules(
                                ext,
                                source,
                                loaded_presets,
                                src,
                            )
                        )
                    case _:
                        pass
                tier2_raw.extend(local_rules)
                return [ScopedRule(rule=r) for r in tier2_raw]
