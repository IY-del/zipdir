"""Runtime path evaluation, smart remapping, and non-greedy directory pruning."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from zipdir.interpreter import RuleInterpreter
from zipdir.models import EvaluationResult, IgnoreRule, RuleKind, ScopedRule


@dataclass
class _AncestorStatus:
    is_excluded: bool = False
    shallowest_excluded_ancestor: PurePosixPath | None = None
    matched_rule: IgnoreRule | None = None


class PathEvaluator:
    """Evaluates relative paths against compiled .zipignore rules with hierarchical phagocytosis."""

    rules: tuple[IgnoreRule, ...]

    def __init__(
        self,
        rules: Sequence[IgnoreRule | str | ScopedRule] = (),
        interpreter: RuleInterpreter | None = None,
    ) -> None:
        if all(isinstance(r, IgnoreRule) for r in rules):
            self.rules = tuple(r for r in rules if isinstance(r, IgnoreRule))
        else:
            compiler = interpreter or RuleInterpreter()
            self.rules = compiler.compile_all(rules)

    def evaluate(self, rel_path: PurePosixPath, is_dir: bool = False) -> EvaluationResult:
        """Evaluate path against rules, returning EvaluationResult(is_excluded, arc_path, matched_rule)."""
        status = self._evaluate_ancestors(rel_path.parts)
        is_excluded, excluded_by, rescued_by = self._evaluate_target(rel_path, is_dir, status)

        if is_excluded:
            return EvaluationResult(True, None, excluded_by)
        if rescued_by is None:
            return EvaluationResult(False, rel_path, None)

        arc_rel = self._remap_path(rel_path, rescued_by, status.shallowest_excluded_ancestor)
        return EvaluationResult(False, arc_rel, rescued_by)

    def should_prune(self, rel_dir: PurePosixPath) -> bool:
        """Check if an excluded directory has any active rescue rules that could target its contents."""
        if not self.evaluate(rel_dir, is_dir=True).is_excluded:
            return False

        posix_str = rel_dir.as_posix()
        for r in self.rules:
            if r.kind != RuleKind.RESCUE:
                continue
            if r.scope != PurePosixPath():
                if r.scope == rel_dir or r.scope.is_relative_to(rel_dir):
                    return False
                if not rel_dir.is_relative_to(r.scope):
                    continue
            clean_pat = r.pattern.lstrip("/")
            full_pat = (r.scope / clean_pat).as_posix() if r.scope != PurePosixPath() else clean_pat
            if full_pat.startswith(posix_str) or posix_str.startswith(full_pat.split("*")[0]):
                return False

        return True

    def _evaluate_ancestors(self, parts: tuple[str, ...]) -> _AncestorStatus:
        status = _AncestorStatus()
        for k in range(1, len(parts)):
            anc = PurePosixPath(*parts[:k])
            anc_str = anc.as_posix()
            for r in self.rules:
                match_str = self._scoped_target(anc, anc_str, r.scope)
                if match_str is None or not r.regex.search(match_str):
                    continue
                if r.kind == RuleKind.EXCLUDE:
                    status.is_excluded = True
                    if status.shallowest_excluded_ancestor is None:
                        status.shallowest_excluded_ancestor = anc
                    status.matched_rule = r
                elif r.kind == RuleKind.RESCUE:
                    status.is_excluded = False
                    status.matched_rule = r
                elif r.kind == RuleKind.REDELETE:
                    status.is_excluded = True
                    status.matched_rule = r
        return status

    def _evaluate_target(
        self, rel_path: PurePosixPath, is_dir: bool, status: _AncestorStatus
    ) -> tuple[bool, IgnoreRule | None, IgnoreRule | None]:
        posix_str = rel_path.as_posix()
        is_excluded = status.is_excluded
        matched = status.matched_rule
        rescued_by = matched if (matched and matched.kind == RuleKind.RESCUE) else None
        excluded_by = matched if is_excluded else None

        for r in self.rules:
            if r.is_dir_only and not is_dir:
                continue
            target_str = self._scoped_target(rel_path, posix_str, r.scope)
            if target_str is None or not r.regex.search(target_str):
                continue

            if r.kind == RuleKind.RESCUE:
                rescued_by = r
                excluded_by = None
                is_excluded = False
            elif r.kind == RuleKind.REDELETE:
                if self._redelete_matches_rescue(r.target, rescued_by):
                    rescued_by = None
                    excluded_by = r
                    is_excluded = True
            else:
                excluded_by = r
                rescued_by = None
                is_excluded = True

        return is_excluded, excluded_by, rescued_by

    def _remap_path(
        self,
        rel_path: PurePosixPath,
        rescued_by: IgnoreRule,
        shallowest_excluded_ancestor: PurePosixPath | None,
    ) -> PurePosixPath:
        target = rescued_by.target
        scope = rescued_by.scope
        if target in (".", "./"):
            return rel_path

        has_ancestor = shallowest_excluded_ancestor is not None
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

        if target in ("?", "?/"):
            if has_ancestor:
                dest_dir = anchor_parent
            else:
                if rel_path.parent == PurePosixPath("."):
                    return rel_path
                dest_dir = anchor_parent.parent
        elif target in ("..", "../"):
            dest_dir = anchor_parent.parent
        elif target.startswith("/"):
            dest_dir = PurePosixPath(target.lstrip("/"))
        elif scope != PurePosixPath():
            dest_dir = scope / target
        else:
            base_str = anchor_parent.as_posix() if anchor_parent != PurePosixPath(".") else ""
            comb = os.path.normpath(os.path.join(base_str, target)).lstrip("./")
            dest_dir = PurePosixPath(comb) if comb and comb != "." else PurePosixPath()

        if dest_dir == PurePosixPath("."):
            dest_dir = PurePosixPath()
        return dest_dir / sub_path if dest_dir != PurePosixPath() else sub_path

    def _scoped_target(
        self, path: PurePosixPath, posix_str: str, scope: PurePosixPath
    ) -> str | None:
        if scope == PurePosixPath():
            return posix_str
        if not path.is_relative_to(scope) or path == scope:
            return None
        return path.relative_to(scope).as_posix()

    def _redelete_matches_rescue(self, redelete_target: str, rescued_by: IgnoreRule | None) -> bool:
        if not redelete_target or rescued_by is None:
            return True
        r_target = rescued_by.target
        if redelete_target in (
            r_target,
            r_target.lstrip("/"),
            r_target.rstrip("/"),
            f"?/{r_target}",
            r_target.removeprefix("?/"),
        ):
            return True
        return redelete_target == "?" and r_target in ("?", "?/")


def evaluate_path(
    rel_path: PurePosixPath,
    is_dir: bool,
    rules: Sequence[IgnoreRule],
) -> tuple[bool, PurePosixPath | None, IgnoreRule | None]:
    """Evaluate path against rules, returning (is_excluded, arc_rel_path, matched_rule)."""
    res = PathEvaluator(rules).evaluate(rel_path, is_dir=is_dir)
    return res.is_excluded, res.arc_path, res.matched_rule
