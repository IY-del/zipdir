"""Interfaces and FactoryMethod metaclass for preset loading, C3 linearization, and cascading."""

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from zipdir.interfaces.interpreter import IRuleSqueezer
from zipdir.interfaces.models import DPreset, DScopedRule, MInterface


class MPresetCatalog(MInterface):
    """FactoryMethod metaclass for IPresetCatalog."""

    def __call__(cls, *args: object, **kwargs: object) -> "IPresetCatalog":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DPresetCatalog:
    """State invariant for preset discovery and C3 cascade resolution."""

    preset_dirs: list[Path]
    interpreter: IRuleSqueezer


class IPresetCatalog(DPresetCatalog, metaclass=MPresetCatalog):
    """Nominal interface for preset loading, C3 linearization, and 4-tier cascading."""

    def parse_file(self, file: Path) -> DPreset:
        raise NotImplementedError

    def load_all(self) -> dict[str, DPreset]:
        raise NotImplementedError

    def linearize_presets(
        self,
        name: str,
        raw_presets: Mapping[str, DPreset],
    ) -> list[str]:
        raise NotImplementedError

    def discover_sub_zipignores(self, source: Path) -> list[tuple[PurePosixPath, Path]]:
        raise NotImplementedError

    def resolve_cascade(
        self,
        source: Path,
        presets: Mapping[str, DPreset] | None = None,
        *,
        preset: str | None = None,
        cli_rules: Sequence[str] = (),
        no_default_rules: bool = False,
    ) -> tuple[str, list[str | DScopedRule]]:
        raise NotImplementedError
