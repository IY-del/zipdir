"""Output package exporting the final fallback OutputResolver and strategies."""

from pathlib import Path

from zipdir.output.fallback import OutputResolver
from zipdir.output.strategies import (
    DEFAULT_OUTPUT_TARGET_STRATEGIES,
    AbsoluteOutputStrategy,
    BareParentOutputStrategy,
    CwdRelativeOutputStrategy,
    ParentRelativeOutputStrategy,
)


def resolve_output_path(
    source: Path,
    name: str,
    output_target: str | Path | None,
    timestamp: bool = False,
    *,
    force: bool = False,
    cwd: Path | None = None,
) -> Path:
    """Resolve and normalize destination archive path (defaults to current working directory)."""
    return OutputResolver(cwd=cwd).resolve(
        source,
        name,
        output_target,
        timestamp=timestamp,
        force=force,
    )


__all__ = [
    "AbsoluteOutputStrategy",
    "BareParentOutputStrategy",
    "CwdRelativeOutputStrategy",
    "DEFAULT_OUTPUT_TARGET_STRATEGIES",
    "OutputResolver",
    "ParentRelativeOutputStrategy",
    "resolve_output_path",
]
