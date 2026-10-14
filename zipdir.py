#!/usr/bin/env python3
"""Package a directory into a clean ZIP archive with .zipignore rules and smart path remapping."""

import sys
from pathlib import Path

# Ensure package directory is on sys.path when invoked as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from zipdir.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
