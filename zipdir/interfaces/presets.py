"""Interfaces for preset catalogs and cascading rule resolution."""

from collections.abc import Sequence
from pathlib import Path

from zipdir.models import PresetModel, ScopedRule


class IPresetCatalog:
    """Interface for discovering, loading, and cascading .zipignore presets."""

    def get(self, name: str) -> PresetModel | None:
        raise NotImplementedError

    def list(self) -> list[PresetModel]:
        raise NotImplementedError

    def resolve_cascade(
        self,
        root_dir: Path,
        preset_name: str = "default",
        extra_rules: Sequence[str] = (),
    ) -> tuple[ScopedRule, ...]:
        raise NotImplementedError
