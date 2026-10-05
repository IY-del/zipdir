"""zipdir package: Smart directory packaging with .zipignore rules and remapping."""

from zipdir.cli import app, package
from zipdir.evaluator import evaluate_path
from zipdir.glob import GlobExpression
from zipdir.interpreter import RuleInterpreter, compile_rule
from zipdir.models import (
    IgnoreRule,
    PackagerConfig,
    ParsedRule,
    PresetModel,
    RuleKind,
)
from zipdir.packager import ZipPackager
from zipdir.presets import (
    DEFAULT_PRESET_DIRS,
    load_presets,
    load_raw_zipignore_preset,
)
from zipdir.squeezer import squeeze_rules

__all__ = [
    "DEFAULT_PRESET_DIRS",
    "GlobExpression",
    "IgnoreRule",
    "PackagerConfig",
    "ParsedRule",
    "PresetModel",
    "RuleInterpreter",
    "RuleKind",
    "ZipPackager",
    "app",
    "compile_rule",
    "evaluate_path",
    "load_presets",
    "load_raw_zipignore_preset",
    "package",
    "squeeze_rules",
]
