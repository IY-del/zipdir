"""Runtime path evaluation and hierarchical RuleKind phagocytosis."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from zipdir.models import IgnoreRule, RuleKind


@dataclass
class _PathStatus:
    is_excluded: bool = False
    shallowest_excluded_ancestor: PurePosixPath | None = None
    matched_rule: IgnoreRule | None = None


def evaluate_path(
    rel_path: PurePosixPath,
    is_dir: bool,
    rules: Sequence[IgnoreRule],
) -> tuple[bool, PurePosixPath | None, IgnoreRule | None]:
    """Evaluate path against rules, returning (is_excluded, arc_rel_path, matched_rule).
    Implements RuleKind phagocytosis (貪食):
    - Ancestors to descendants: EXCLUDE excludes subtree; RESCUE eats EXCLUDE for subtree; REDELETE eats RESCUE.
    - Path-level rules: RESCUE eats EXCLUDE/REDELETE; REDELETE eats matching RESCUE; EXCLUDE eats RESCUE.
    - Lazy exile route ('?'): dynamically resolves exile parent relative to shallowest excluded ancestor.
    """
    posix_str = rel_path.as_posix()
    parts = rel_path.parts

    # 1. Hierarchical ancestor evaluation (top-down engulfment)
    status = _PathStatus()
    for k in range(1, len(parts)):
        anc = PurePosixPath(*parts[:k])
        anc_str = anc.as_posix()
        for r in rules:
            if r.regex.search(anc_str):
                if r.kind == RuleKind.EXCLUDE:
                    status.is_excluded = True
                    if status.shallowest_excluded_ancestor is None:
                        status.shallowest_excluded_ancestor = anc
                    status.matched_rule = r
                elif r.kind == RuleKind.RESCUE:
                    # RESCUE eats EXCLUDE for this ancestor and its descendants
                    status.is_excluded = False
                    status.matched_rule = r
                elif r.kind == RuleKind.REDELETE:
                    # REDELETE eats RESCUE for this ancestor and its descendants
                    status.is_excluded = True
                    status.matched_rule = r

    # 2. File / target level evaluation (eats inherited ancestor status)
    is_excluded = status.is_excluded
    shallowest_excluded_ancestor = status.shallowest_excluded_ancestor
    matched_rule = status.matched_rule
    rescued_by = matched_rule if (matched_rule and matched_rule.kind == RuleKind.RESCUE) else None
    excluded_by = matched_rule if is_excluded else None

    for r in rules:
        if r.is_dir_only and not is_dir:
            continue
        if r.regex.search(posix_str):
            if r.kind == RuleKind.RESCUE:
                rescued_by = r
                excluded_by = None
                is_excluded = False
            elif r.kind == RuleKind.REDELETE:
                if (
                    not r.target
                    or rescued_by is None
                    or rescued_by.target.rstrip("/") == r.target.rstrip("/")
                ):
                    rescued_by = None
                    excluded_by = r
                    is_excluded = True
            else:
                excluded_by = r
                rescued_by = None
                is_excluded = True

    if is_excluded:
        return True, None, excluded_by

    if rescued_by is None:
        return False, rel_path, None

    # 3. Smart remapping with lazy resolution of exile '?'
    target = rescued_by.target
    if shallowest_excluded_ancestor is not None:
        ancestor = shallowest_excluded_ancestor
        sub_path = rel_path.relative_to(ancestor)
        if target in (".", "./"):
            arc_rel = rel_path
        elif target in ("?", "?/"):
            p_parent = ancestor.parent if ancestor.parent != PurePosixPath(".") else PurePosixPath()
            arc_rel = p_parent / sub_path if p_parent != PurePosixPath() else sub_path
        elif target.startswith("/"):
            dest_dir = PurePosixPath(target.lstrip("/"))
            arc_rel = dest_dir / sub_path if dest_dir != PurePosixPath() else sub_path
        else:
            p_parent_str = (
                ancestor.parent.as_posix() if ancestor.parent != PurePosixPath(".") else ""
            )
            comb = os.path.normpath(os.path.join(p_parent_str, target)).lstrip("./")
            dest_dir = PurePosixPath(comb) if comb and comb != "." else PurePosixPath()
            arc_rel = dest_dir / sub_path if dest_dir != PurePosixPath() else sub_path
    else:
        if target in (".", "./"):
            arc_rel = rel_path
        elif target in ("?", "?/"):
            if rel_path.parent == PurePosixPath("."):
                arc_rel = rel_path
            else:
                p_parent = (
                    rel_path.parent.parent
                    if rel_path.parent.parent != PurePosixPath(".")
                    else PurePosixPath()
                )
                arc_rel = (
                    p_parent / rel_path.name
                    if p_parent != PurePosixPath()
                    else PurePosixPath(rel_path.name)
                )
        elif target.startswith("/"):
            dest_dir = PurePosixPath(target.lstrip("/"))
            arc_rel = (
                dest_dir / rel_path.name
                if dest_dir != PurePosixPath()
                else PurePosixPath(rel_path.name)
            )
        else:
            p_str = rel_path.parent.as_posix() if rel_path.parent != PurePosixPath(".") else ""
            comb = os.path.normpath(os.path.join(p_str, target)).lstrip("./")
            dest_dir = PurePosixPath(comb) if comb and comb != "." else PurePosixPath()
            arc_rel = (
                dest_dir / rel_path.name
                if dest_dir != PurePosixPath()
                else PurePosixPath(rel_path.name)
            )

    return False, arc_rel, rescued_by
