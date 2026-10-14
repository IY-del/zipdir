"""zipdir package: Smart directory packaging with .zipignore rules and remapping."""

from zipdir.cli import ZipdirCommand, app, package
from zipdir.evaluator import PathEvaluator, evaluate_path
from zipdir.glob import GlobExpression
from zipdir.interpreter import compile_rule
from zipdir.models import (
    EvaluationResult,
    IgnoreRule,
    PackagerConfig,
    ParsedRule,
    PresetModel,
    RuleKind,
    ScopedRule,
)
from zipdir.output import OutputResolver, ResolvedOutput, resolve_output_path
from zipdir.packager import ZipPackager
from zipdir.presets import (
    DEFAULT_PRESET_DIRS,
    PresetCatalog,
    discover_sub_zipignores,
    load_presets,
    load_raw_zipignore_preset,
)
from zipdir.squeezer import RuleInterpreter, squeeze_rules
from zipdir.ui import ConsoleReporter, format_size

__all__ = [
    "ConsoleReporter",
    "DEFAULT_PRESET_DIRS",
    "EvaluationResult",
    "GlobExpression",
    "IgnoreRule",
    "OutputResolver",
    "PackagerConfig",
    "ParsedRule",
    "PathEvaluator",
    "PresetCatalog",
    "PresetModel",
    "ResolvedOutput",
    "RuleInterpreter",
    "RuleKind",
    "ScopedRule",
    "ZipPackager",
    "ZipdirCommand",
    "app",
    "compile_rule",
    "discover_sub_zipignores",
    "evaluate_path",
    "format_size",
    "load_presets",
    "load_raw_zipignore_preset",
    "package",
    "resolve_output_path",
    "squeeze_rules",
]
