"""Non-greedy pruning path evaluator via progressive inheritance over remapped.PathEvaluator."""

from pathlib import PurePosixPath

from zipdir.evaluator.remapped import PathEvaluator as RemappedPathEvaluator
from zipdir.interfaces.models import RuleKind
from zipdir.models import IgnoreRule


class PathEvaluator(RemappedPathEvaluator):
    """Extends RemappedPathEvaluator with non-greedy directory pruning (`should_prune`)."""

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        """Check if an excluded directory has any active rescue rules that could target its contents."""
        if not self.evaluate(rel_dir, is_dir=True).is_excluded:
            return False

        posix_str = rel_dir.as_posix()
        return not any(
            self._rule_can_rescue_under(r, rel_dir, posix_str)
            for r in self.rules
            if r.kind == RuleKind.RESCUE
        )

    def _rule_can_rescue_under(
        self, rule: IgnoreRule, rel_dir: PurePosixPath, posix_str: str
    ) -> bool:
        if rule.scope != PurePosixPath():
            if rule.scope == rel_dir or rule.scope.is_relative_to(rel_dir):
                return True
            if not rel_dir.is_relative_to(rule.scope):
                return False
        clean_pat = rule.pattern.lstrip("/")
        full_pat = (
            (rule.scope / clean_pat).as_posix() if rule.scope != PurePosixPath() else clean_pat
        )
        return full_pat.startswith(posix_str) or posix_str.startswith(full_pat.split("*")[0])
