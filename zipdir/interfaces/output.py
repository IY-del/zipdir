"""Interfaces and FactoryMethod metaclass for 3-tier output path resolution."""

from collections.abc import Callable, Sequence
from pathlib import Path

from zipdir.interfaces.models import DResolvedOutput, MInterface


class IOutputTargetStrategy:
    """Nominal Strategy interface for classifying 3-tier raw output path prefixes."""

    def matches(self, raw: str) -> bool:
        raise NotImplementedError

    def classify(self, source: Path, cwd: Path, raw: str) -> tuple[Path, bool]:
        raise NotImplementedError


class MOutputResolver(MInterface):
    """FactoryMethod metaclass for IOutputResolver."""

    def __call__(cls, *args: object, **kwargs: object) -> "IOutputResolver":
        return super().__call__(*args, **kwargs)  # type: ignore[return-value]


class DOutputResolver:
    """State invariant for output path resolvers."""

    cwd: Path
    timestamp_fn: Callable[[], str]
    target_strategies: Sequence[IOutputTargetStrategy]


class IOutputResolver(DOutputResolver, metaclass=MOutputResolver):
    """Nominal interface for 3-tier output path resolution and collision fallback."""

    def normalize_cli_args(self, args: Sequence[str]) -> list[str]:
        raise NotImplementedError

    def resolve_with_metadata(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> DResolvedOutput:
        raise NotImplementedError

    def resolve(
        self,
        source: Path,
        name: str,
        output_target: str | Path | None = None,
        *,
        timestamp: bool = False,
        force: bool = False,
    ) -> Path:
        raise NotImplementedError
