"""Command Line Interface for zipdir."""

import sys
import time
from pathlib import Path
from typing import Annotated

import typer

from zipdir.models import PackagerConfig, PresetModel, ScopedRule
from zipdir.packager import ZipPackager
from zipdir.presets import (
    discover_sub_zipignores,
    load_presets,
    load_raw_zipignore_preset,
)
from zipdir.squeezer import squeeze_rules
from zipdir.ui import (
    color_bold,
    color_cyan,
    color_dim,
    color_yellow,
)

app = typer.Typer(
    name="zipdir",
    help="Package a directory into a clean ZIP archive with .zipignore rules and smart path remapping.",
    add_completion=False,
    no_args_is_help=False,
)


def resolve_output_path(
    source: Path, name: str, output_target: Path | None, timestamp: bool = False
) -> Path:
    """Resolve and normalize destination archive path (defaults to source.parent per Plan B)."""
    default_filename = (
        f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.zip" if timestamp else f"{name}.zip"
    )
    if output_target is None:
        target = source.parent / default_filename
    else:
        target = output_target.expanduser()
        if target.is_dir():
            target = target / default_filename
        else:
            if not target.name.endswith(".zip"):
                target = target.with_suffix(".zip")
            if len(target.parts) == 1:
                target = source.parent / target.name
    return target.parent.resolve() / target.name


def print_presets(presets: dict[str, PresetModel]) -> None:
    """Display available presets and their configurations."""
    print(color_bold("\nAvailable zipdir presets:\n"))
    for name, p in presets.items():
        src_info = f"({p.source_path})" if p.source_path else "(built-in)"
        extends_info = f" [extends {', '.join(p.extends)}]" if p.extends else ""
        print(
            f"  {color_cyan(name):<12} {color_bold(p.description)}{color_dim(extends_info)} {color_dim(src_info)}"
        )
        if p.rules:
            rules_str = ", ".join(p.rules)
            print(f"    {color_dim('• Rules:')} {rules_str}")
        print()


@app.command(
    epilog="""\
Preset configuration:
  Presets are loaded from ~/.dcfg/config/zipdir/presets/*.zipignore or project presets/*.zipignore.
  Presets can extend existing presets using '# inherit: <name1>, <name2>'.
  To list available presets and their rules:
    zipdir --list-presets

Rule syntax:
  - 'out/'               # Exclude out/ directory
  - '!out/*.pdf'         # Rescue out/*.pdf and lift to parent (shorthand for ?/!out/*.pdf)
  - './!out/*.pdf'       # Rescue out/*.pdf keeping original directory hierarchy (階層死守)
  - '?/!out/*.pdf'       # Rescue out/*.pdf escaping excluded folder to parent (亡命ルート)
  - '{to}!out/*.pdf'     # Rescue and move to {to} relative to scope (e.g. 'dist!out/*.pdf')
  - '/{to}!out/*.pdf'    # Rescue and move to {to} relative to archive root
  - '!{to}!out/*.pdf'    # Re-delete previously rescued item (!{to}! cancels rescue, '!!' cancels any)

Examples:
  zipdir                                  # Packages current directory to ../<dir>.zip
  zipdir -t                               # Packages current directory with timestamp: ../<dir>_<timestamp>.zip
  zipdir final.zip                        # Packages current directory to ../final.zip
  zipdir report                           # Packages report/ with default 'clean' preset
  zipdir report final.zip --preset report # Packages report/ with 'report' preset
  zipdir -o /tmp/                         # Outputs <name>.zip inside /tmp/
  zipdir -o /tmp/ -t                      # Outputs <name>_<timestamp>.zip inside /tmp/
  zipdir final.zip -f                     # Overwrite existing final.zip
  zipdir --dry-run                        # Preview archive contents without creating file
""",
)
def package(
    directory: Annotated[
        Path | None,
        typer.Argument(help="Target directory to package (default: current directory '.')"),
    ] = None,
    output_path: Annotated[
        Path | None,
        typer.Argument(help="Optional ZIP output path (positional alternative to -o)"),
    ] = None,
    preset: Annotated[
        str | None,
        typer.Option(
            "--preset",
            help="Packaging preset name (defaults to 'clean' or local .zipignore inherit)",
        ),
    ] = None,
    list_presets: Annotated[
        bool,
        typer.Option("--list-presets", help="List all available presets and exit"),
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("-x", "--exclude", help="Additional exclusion patterns; repeatable"),
    ] = None,
    rule: Annotated[
        list[str] | None,
        typer.Option(
            "-r",
            "--rule",
            help="Additional rules (rescue !{to}!, re-delete !!); repeatable",
        ),
    ] = None,
    keep: Annotated[
        list[str] | None,
        typer.Option("-k", "--keep", help="Remove exact patterns from preset rules; repeatable"),
    ] = None,
    no_default_rules: Annotated[
        bool,
        typer.Option(
            "--no-default-rules",
            "--no-default-excludes",
            help="Ignore preset rules",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="Explicit ZIP output path or directory"),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Archive root directory name and default filename prefix"),
    ] = None,
    timestamp: Annotated[
        bool,
        typer.Option(
            "-t",
            "--timestamp",
            help="Append timestamp to default output filename (e.g. <name>_<timestamp>.zip; default: False)",
        ),
    ] = False,
    flat: Annotated[
        bool,
        typer.Option("--flat", help="Omit enclosing top-level directory in ZIP"),
    ] = False,
    compression: Annotated[
        int,
        typer.Option(
            "--compression",
            min=0,
            max=9,
            help="ZIP compression level (0=store, 1..9=deflate; default: 6)",
        ),
    ] = 6,
    force: Annotated[
        bool,
        typer.Option("-f", "--force", help="Overwrite output file if it already exists"),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("-v", "--verbose", help="Print details of rescued and excluded items"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show resulting members without creating ZIP"),
    ] = False,
) -> None:
    presets = load_presets()

    if list_presets:
        print_presets(presets)
        return

    # Smart positional argument resolution (defaults directory to '.' per Plan B)
    target_dir: Path
    target_out_arg: Path | None = output

    if directory is None:
        target_dir = Path(".")
    elif output_path is None and str(directory).endswith(".zip"):
        target_dir = Path(".")
        if target_out_arg is None:
            target_out_arg = directory
    else:
        target_dir = directory
        if target_out_arg is None:
            target_out_arg = output_path

    source = target_dir.expanduser().resolve()
    if not source.is_dir():
        print(f"{color_yellow('Error:')} Not a directory: {source}", file=sys.stderr)
        raise typer.Exit(code=1)

    archive_name = name if name is not None else source.name
    if (
        not archive_name
        or archive_name in (".", "..")
        or "/" in archive_name
        or "\\" in archive_name
    ):
        print(
            f"{color_yellow('Error:')} --name must be a nonempty single directory name",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)

    # Local .zipignore detection and inheritance
    local_zipignore = source / ".zipignore"
    local_rules: list[str] = []
    local_extends: list[str] = []
    if local_zipignore.is_file():
        local_model = load_raw_zipignore_preset(local_zipignore)
        local_rules = local_model.rules
        local_extends = local_model.extends

    # Determine active preset(s)
    effective_preset_name = preset
    if effective_preset_name is None:
        if local_extends:
            effective_preset_name = ", ".join(local_extends)
        else:
            effective_preset_name = "clean"

    # Resolve base rules (from explicit preset or local_extends)
    base_rules: list[str] = []
    if not no_default_rules:
        if preset is not None:
            if preset not in presets:
                print(
                    f"{color_yellow('Error:')} Unknown preset '{preset}'. Available: {', '.join(presets.keys())}",
                    file=sys.stderr,
                )
                raise typer.Exit(code=1)
            base_rules.extend(presets[preset].rules)
        elif local_extends:
            for parent in local_extends:
                if parent in presets:
                    for r in presets[parent].rules:
                        if r not in base_rules:
                            base_rules.append(r)
                else:
                    print(
                        f"zipdir: warning: preset '{parent}' declared in .zipignore not found",
                        file=sys.stderr,
                    )
        else:
            if "clean" in presets:
                base_rules.extend(presets["clean"].rules)

    # 4-tier Python-like scoping resolution:
    # 1. Preset (Built-in)
    keep_set = set(keep or [])
    tier1_rules: list[ScopedRule] = [ScopedRule(rule=p) for p in base_rules if p not in keep_set]

    # 2. Root .zipignore (Global)
    tier2_rules: list[ScopedRule] = [ScopedRule(rule=r) for r in local_rules]

    # 3. Subdirectory .zipignores (Enclosing / Local, ordered by depth)
    tier3_rules: list[ScopedRule] = []
    sub_zipignores = discover_sub_zipignores(source)
    for rel_dir, sub_file in sub_zipignores:
        sub_model = load_raw_zipignore_preset(sub_file)
        for r in sub_model.rules:
            tier3_rules.append(ScopedRule(scope=rel_dir, rule=r))

    # 4. Command arguments (CLI Overrides)
    cli_rules: list[str] = (exclude or []) + (rule or [])
    tier4_rules: list[ScopedRule] = [ScopedRule(rule=r) for r in cli_rules]

    combined_raw: list[ScopedRule] = tier1_rules + tier2_rules + tier3_rules + tier4_rules
    combined_rules = squeeze_rules(combined_raw)

    resolved_output = resolve_output_path(source, archive_name, target_out_arg, timestamp=timestamp)

    config = PackagerConfig(
        source=source,
        output=resolved_output,
        name=archive_name,
        preset_name=effective_preset_name,
        rules=combined_rules,
        compression=compression,
        flat=flat,
        dry_run=dry_run,
        force=force,
        verbose=verbose,
    )

    packager = ZipPackager(config)
    try:
        packager.package()
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        print(f"{color_yellow('Error:')} {e}", file=sys.stderr)
        raise typer.Exit(code=1)
