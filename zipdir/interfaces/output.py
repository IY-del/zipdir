"""Interfaces for output path resolution."""

from pathlib import Path

from zipdir.models import ResolvedOutput


class IOutputTargetStrategy:
    """Strategy interface for output destination target resolution."""

    def match(self, raw: str) -> bool:
        raise NotImplementedError

    def resolve(self, raw: str, source_path: Path, package_name: str) -> ResolvedOutput:
        raise NotImplementedError


class IOutputResolver:
    """Interface for resolving output paths and detecting fallback collisions."""

    strategies: tuple[IOutputTargetStrategy, ...]

    def resolve(
        self,
        source_path: Path,
        output_target: Path | str | None,
        package_name: str | None = None,
    ) -> ResolvedOutput:
        raise NotImplementedError
