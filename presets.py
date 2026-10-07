"""Preset definition, loading, and resolution from configuration directories."""

import os
import sys
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from zipdir.models import PresetModel
from zipdir.squeezer import squeeze_rules

DEFAULT_PRESET_DIRS: list[Path] = [
    Path.home() / ".dcfg" / "config" / "zipdir" / "presets",
    Path(__file__).resolve().parent.parent.parent / "config" / "zipdir" / "presets",
    Path.home() / ".config" / "zipdir" / "presets",
]


def load_raw_zipignore_preset(file: Path) -> PresetModel:
    """Parse a .zipignore preset file extracting description, inherit/extends, and rule lines."""
    content = file.read_text(encoding="utf-8")
    description = ""
    extends: list[str] = []
    rules: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            lower = stripped.lower()
            if any(k in lower for k in ["inherit:", "extends:", "include:"]):
                val = stripped.split(":", 1)[1]
                for p in val.split(","):
                    p_clean = p.strip()
                    if p_clean and p_clean not in extends:
                        extends.append(p_clean)
            elif "description:" in lower:
                description = stripped.split(":", 1)[1].strip()
            continue
        rules.append(stripped)

    stem = file.name
    if stem.endswith(".zipignore"):
        stem = stem.removesuffix(".zipignore")
    elif stem.endswith(".yaml") or stem.endswith(".yml"):
        stem = file.stem

    return PresetModel(
        name=stem,
        description=description,
        rules=rules,
        extends=extends,
        source_path=file,
    )


def load_presets(preset_dirs: Sequence[Path] | None = None) -> dict[str, PresetModel]:
    """Discover and load presets from configuration directories, resolving inheritance with rule squeezing."""
    raw_presets: dict[str, PresetModel] = {}

    dirs = list(preset_dirs) if preset_dirs is not None else list(DEFAULT_PRESET_DIRS)
    if "ZIPDIR_PRESETS_DIR" in os.environ:
        dirs.insert(0, Path(os.environ["ZIPDIR_PRESETS_DIR"]))

    for directory in dirs:
        if not directory.is_dir():
            continue
        found_files = (
            sorted(directory.glob("*.zipignore"))
            + sorted(directory.glob("*.yaml"))
            + sorted(directory.glob("*.yml"))
        )
        for file in found_files:
            stem = file.name.removesuffix(".zipignore")
            if stem.endswith(".yaml") or stem.endswith(".yml"):
                stem = file.stem
            if stem not in raw_presets:
                try:
                    raw_presets[stem] = load_raw_zipignore_preset(file)
                except Exception as e:
                    print(f"zipdir: warning: failed to parse preset '{file}': {e}", file=sys.stderr)

    presets: dict[str, PresetModel] = {}

    def resolve(name: str, visited: list[str]) -> tuple[str, list[str], Path | None]:
        if name in visited:
            raise ValueError(
                f"Circular dependency in preset inheritance: {' -> '.join(visited)} -> {name}"
            )
        visited.append(name)

        if name not in raw_presets:
            raise ValueError(f"Preset '{name}' not found in configuration directories")

        model = raw_presets[name]
        desc = model.description
        rules = list(model.rules)
        parents = model.extends
        src_file = model.source_path

        merged_rules: list[str] = []
        inherited_desc = desc
        for parent in parents:
            p_desc, p_rules, _ = resolve(parent, visited.copy())
            merged_rules.extend(p_rules)
            if not inherited_desc:
                inherited_desc = p_desc

        merged_rules.extend(rules)
        merged_rules = [r if isinstance(r, str) else r.rule for r in squeeze_rules(merged_rules)]
        return inherited_desc, merged_rules, src_file

    for name in raw_presets:
        try:
            desc, rules, src = resolve(name, [])
            presets[name] = PresetModel(
                name=name,
                description=desc,
                rules=rules,
                extends=raw_presets[name].extends,
                source_path=src,
            )
        except Exception as e:
            print(f"zipdir: warning: failed to resolve preset '{name}': {e}", file=sys.stderr)

    return presets


def discover_sub_zipignores(source: Path) -> list[tuple[PurePosixPath, Path]]:
    """Discover all .zipignore files in subdirectories under source, sorted by depth."""
    found: list[tuple[PurePosixPath, Path]] = []
    for dirpath, dirnames, filenames in source.walk(follow_symlinks=False):
        # Do not traverse VCS directories
        dirnames[:] = [d for d in dirnames if d not in (".git", ".svn", ".hg")]
        if dirpath == source:
            continue
        if ".zipignore" in filenames:
            rel_dir = PurePosixPath(dirpath.relative_to(source).as_posix())
            found.append((rel_dir, dirpath / ".zipignore"))
    # Sort by depth (shallowest first), then path
    found.sort(key=lambda item: (len(item[0].parts), item[0].as_posix()))
    return found
