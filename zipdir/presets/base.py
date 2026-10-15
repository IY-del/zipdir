"""Minimal concrete preset file parser and base cascade skeleton (base stage for progressive inheritance)."""

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from zipdir.interfaces.interpreter import IRuleSqueezer, MRuleSqueezer
from zipdir.interfaces.models import DPreset
from zipdir.interfaces.presets import IPresetCatalog
from zipdir.models import PresetModel, ScopedRule

DEFAULT_PRESET_DIRS: list[Path] = [
    Path(__file__).resolve().parent.parent.parent / "presets",
    Path(__file__).resolve().parent.parent / "presets",
    Path.home() / ".config" / "zipdir" / "presets",
    Path.home() / ".dcfg" / "config" / "zipdir" / "presets",
]


def _as_preset_model(preset: DPreset) -> PresetModel:
    if isinstance(preset, PresetModel):
        return preset
    return PresetModel(
        name=preset.name,
        description=preset.description,
        rules=list(preset.rules),
        extends=list(preset.extends),
        source_path=preset.source_path,
    )


class PresetCatalog(IPresetCatalog):
    """Minimal concrete preset catalog with TemplateMethod skeleton for rule cascading."""

    preset_dirs: list[Path]
    interpreter: IRuleSqueezer

    def __init__(
        self,
        preset_dirs: Sequence[Path] | None = None,
        interpreter: IRuleSqueezer | None = None,
        create_interpreter: MRuleSqueezer = IRuleSqueezer,
    ) -> None:
        dirs = list(preset_dirs) if preset_dirs is not None else list(DEFAULT_PRESET_DIRS)
        if "ZIPDIR_PRESETS_DIR" in os.environ:
            dirs.insert(0, Path(os.environ["ZIPDIR_PRESETS_DIR"]))
        self.preset_dirs = dirs
        self.interpreter = interpreter or create_interpreter()

    def parse_file(self, file: Path) -> PresetModel:
        """Parse a .zipignore preset file extracting description, inherit/extends, and rule lines."""
        description = ""
        extends: list[str] = []
        rules: list[str] = []

        for line in file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                description = self._parse_comment_directive(stripped, extends, description)
                continue
            rules.append(stripped)

        return PresetModel(
            name=self._extract_preset_stem(file),
            description=description,
            rules=rules,
            extends=extends,
            source_path=file,
        )

    def load_all(self) -> dict[str, PresetModel]:
        """Minimal raw preset loading (extended with C3 linearization in linearized.py)."""
        return self._discover_raw_presets()

    def linearize_presets(
        self,
        name: str,
        raw_presets: Mapping[str, DPreset],
    ) -> list[str]:
        """Minimal single-node linearization (extended with C3 MRO in linearized.py)."""
        if name not in raw_presets:
            raise ValueError(f"Preset '{name}' not found in configuration directories")
        return [name]

    def discover_sub_zipignores(self, source: Path) -> list[tuple[PurePosixPath, Path]]:
        """Minimal sub-zipignore hook (extended in cascade.py)."""
        return []

    def resolve_cascade(
        self,
        source: Path,
        presets: Mapping[str, DPreset] | None = None,
        *,
        preset: str | None = None,
        cli_rules: Sequence[str] = (),
        no_default_rules: bool = False,
    ) -> tuple[str, list[str | ScopedRule]]:
        """Template skeleton building and squeezing the 4-tier rule cascade."""
        loaded = presets if presets is not None else self.load_all()
        local_model = self._load_root_zipignore(source)
        effective_name = self._determine_preset_name(preset, local_model)

        tier1: list[ScopedRule] = []
        if not no_default_rules:
            base_lines, effective_name = self._collect_tier1_rules(
                source, loaded, preset, local_model, effective_name
            )
            tier1 = [ScopedRule(rule=r) for r in base_lines]

        tier2 = self._collect_tier2_rules(source, loaded, preset, local_model)
        tier3 = self._collect_tier3_rules(source, loaded)
        tier4 = [ScopedRule(rule=r) for r in cli_rules]

        return effective_name, self._squeeze_cascade([*tier1, *tier2, *tier3, *tier4])

    def _load_root_zipignore(self, source: Path) -> PresetModel | None:
        local_file = source / ".zipignore"
        return self.parse_file(local_file) if local_file.is_file() else None

    def _determine_preset_name(self, preset: str | None, local_model: PresetModel | None) -> str:
        if preset is not None:
            return preset
        if local_model is not None and local_model.extends:
            return ", ".join(local_model.extends)
        return "clean"

    def _collect_tier1_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, DPreset],
        preset: str | None,
        local_model: PresetModel | None,
        effective_name: str,
    ) -> tuple[list[str], str]:
        if preset is not None and preset in loaded_presets:
            return list(loaded_presets[preset].rules), effective_name
        if preset is None and "clean" in loaded_presets:
            return list(loaded_presets["clean"].rules), effective_name
        if preset is not None:
            available = ", ".join(loaded_presets.keys())
            raise ValueError(f"Unknown preset '{preset}'. Available: {available}")
        return [], effective_name

    def _collect_tier2_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, DPreset],
        preset: str | None,
        local_model: PresetModel | None,
    ) -> list[ScopedRule]:
        return []

    def _collect_tier3_rules(
        self,
        source: Path,
        loaded_presets: Mapping[str, DPreset],
    ) -> list[ScopedRule]:
        return []

    def _squeeze_cascade(self, combined: Sequence[ScopedRule]) -> list[str | ScopedRule]:
        squeezed = self.interpreter.squeeze(combined)
        return [
            r if isinstance(r, (str, ScopedRule)) else ScopedRule(scope=r.scope, rule=r.rule)
            for r in squeezed
        ]

    def _parse_comment_directive(self, stripped: str, extends: list[str], description: str) -> str:
        lower = stripped.lower()
        if any(k in lower for k in ("inherit:", "extends:", "include:")):
            val = stripped.split(":", 1)[1]
            for p in val.split(","):
                p_clean = p.strip()
                if p_clean and p_clean not in extends:
                    extends.append(p_clean)
        elif "description:" in lower:
            return stripped.split(":", 1)[1].strip()
        return description

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
