"""Models package aggregating data contracts (interface.py) and concrete models (concrete.py)."""

from zipdir.models.concrete import (
    CANONICAL_TARGETS,
    EvaluationResult,
    IgnoreRule,
    PackagerConfig,
    ParsedRule,
    PresetModel,
    ResolvedOutput,
    ScopedRule,
    normalize_posix_path,
    normalize_target,
    redelete_matches_rescue,
)
from zipdir.models.interface import (
    DEvaluationResult,
    DIgnoreRule,
    DPackagerConfig,
    DParsedRule,
    DPreset,
    DResolvedOutput,
    DScopedRule,
    MInterface,
    RuleKind,
)

__all__ = [
    "CANONICAL_TARGETS",
    "DEvaluationResult",
    "DIgnoreRule",
    "DPackagerConfig",
    "DParsedRule",
    "DPreset",
    "DResolvedOutput",
    "DScopedRule",
    "EvaluationResult",
    "IgnoreRule",
    "MInterface",
    "PackagerConfig",
    "ParsedRule",
    "PresetModel",
    "ResolvedOutput",
    "RuleKind",
    "ScopedRule",
    "normalize_posix_path",
    "normalize_target",
    "redelete_matches_rescue",
]
