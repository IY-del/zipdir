"""Interface for packaging progress reporting."""

from pathlib import Path

from zipdir.models import PackagerConfig


class IReporter:
    """Interface for console output reporting during packaging."""

    def report_start(self, config: PackagerConfig) -> None:
        raise NotImplementedError

    def report_summary(self, path: Path, size: int) -> None:
        raise NotImplementedError
