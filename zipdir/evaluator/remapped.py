"""3-tier coordinate remapping path evaluator via progressive inheritance over base.PathEvaluator."""

from pathlib import PurePosixPath

from zipdir.evaluator.base import PathEvaluator as BasePathEvaluator
from zipdir.evaluator.strategies import RemapContext
from zipdir.models import IgnoreRule


class PathEvaluator(BasePathEvaluator):
    """Extends base PathEvaluator with 3-tier destination coordinate remapping via IRemapStrategy."""

    def _resolve_rescued_path(
        self,
        rel_path: PurePosixPath,
        rescued_by: IgnoreRule,
        shallowest_excluded_ancestor: PurePosixPath | None,
    ) -> PurePosixPath:
        """Dispatch destination archive path calculation to the matching 3-tier IRemapStrategy."""
        sub_path = (
            rel_path.relative_to(shallowest_excluded_ancestor)
            if shallowest_excluded_ancestor is not None
            else PurePosixPath(rel_path.name)
        )
        anchor_parent = (
            shallowest_excluded_ancestor.parent
            if shallowest_excluded_ancestor is not None
            else rel_path.parent
        )
        ctx = RemapContext(
            rel_path=rel_path,
            rescued_by=rescued_by,
            shallowest_excluded_ancestor=shallowest_excluded_ancestor,
            sub_path=sub_path,
            anchor_parent=anchor_parent,
        )
        for strategy in self.remap_strategies:
            if strategy.matches(rescued_by.target):
                return strategy.remap(ctx)
        return super()._resolve_rescued_path(rel_path, rescued_by, shallowest_excluded_ancestor)
