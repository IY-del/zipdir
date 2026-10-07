#!/usr/bin/env python3
"""Package a directory into a clean ZIP archive with .zipignore rules and smart path remapping."""

import sys
from pathlib import Path

# Ensure package directory is on sys.path when invoked as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from zipdir import (  # noqa: E402, F401
    DEFAULT_PRESET_DIRS,
    GlobExpression,
    IgnoreRule,
    PackagerConfig,
    ParsedRule,
    PresetModel,
    RuleInterpreter,
    RuleKind,
    ScopedRule,
    ZipPackager,
    app,
    compile_rule,
    discover_sub_zipignores,
    evaluate_path,
    load_presets,
    load_raw_zipignore_preset,
    package,
    squeeze_rules,
)

if __name__ == "__main__":
    app()
