"""Comprehensive tests for zipdir ignore rule syntax, path evaluation, and packaging engine."""

import zipfile
from pathlib import Path, PurePosixPath

import pytest

from zipdir import (
    GlobExpression,
    IgnoreRule,
    PackagerConfig,
    ParsedRule,
    PresetModel,
    RuleInterpreter,
    RuleKind,
    ScopedRule,
    ZipPackager,
    compile_rule,
    discover_sub_zipignores,
    evaluate_path,
    load_raw_zipignore_preset,
    squeeze_rules,
)
from zipdir.cli import resolve_output_path


# ==============================================================================
# 1. Rule Compiler Tests (Syntax Variations)
# ==============================================================================
class TestRuleCompiler:
    """Tests parsing and compilation of all .zipignore rule syntax variations."""

    def test_comments_and_blank_lines(self) -> None:
        """Comments and empty lines should return None."""
        assert compile_rule("") is None
        assert compile_rule("   ") is None
        assert compile_rule("# This is a comment") is None
        assert compile_rule("   # Indented comment") is None

    def test_standard_exclude_rules(self) -> None:
        """Standard gitignore-style exclusions."""
        r_file = compile_rule("debug.log")
        assert r_file is not None
        assert r_file.kind == RuleKind.EXCLUDE
        assert r_file.pattern == "debug.log"
        assert not r_file.is_dir_only

        r_dir = compile_rule("out/")
        assert r_dir is not None
        assert r_dir.kind == RuleKind.EXCLUDE
        assert r_dir.pattern == "out/"
        assert r_dir.is_dir_only

        r_glob = compile_rule("*.tmp")
        assert r_glob is not None
        assert r_glob.kind == RuleKind.EXCLUDE
        assert r_glob.pattern == "*.tmp"

    def test_rescue_exile_route_default(self) -> None:
        """Default rescue syntax '!{pattern}' defaults to '?' (亡命ルート)."""
        r = compile_rule("!out/*.pdf")
        assert r is not None
        assert r.kind == RuleKind.RESCUE
        assert r.target == "?"
        assert r.pattern == "out/*.pdf"

    def test_rescue_exile_route_explicit(self) -> None:
        """Explicit exile syntax '?/!{pattern}' and '?!{pattern}'."""
        for syntax in ["?/!out/*.pdf", "?!out/*.pdf"]:
            r = compile_rule(syntax)
            assert r is not None, f"Failed to compile {syntax}"
            assert r.kind == RuleKind.RESCUE
            assert r.target in ("?", "?/")
            assert r.pattern == "out/*.pdf"

    def test_rescue_preserve_hierarchy(self) -> None:
        """階層死守 (Preserve original directory hierarchy) syntax: './!{}' and '.!{}'."""
        for syntax in ["./!out/*.pdf", ".!out/*.pdf"]:
            r = compile_rule(syntax)
            assert r is not None, f"Failed to compile {syntax}"
            assert r.kind == RuleKind.RESCUE
            assert r.target in (".", "./")
            assert r.pattern == "out/*.pdf"

    def test_rescue_custom_destination(self) -> None:
        """Custom remapping targets: '{to}!{pattern}'."""
        r1 = compile_rule("dist!out/*.pdf")
        assert r1 is not None
        assert r1.kind == RuleKind.RESCUE
        assert r1.target == "dist"
        assert r1.pattern == "out/*.pdf"

        r2 = compile_rule("dist/bundle!out/*.pdf")
        assert r2 is not None
        assert r2.kind == RuleKind.RESCUE
        assert r2.target == "dist/bundle"
        assert r2.pattern == "out/*.pdf"

    def test_rescue_archive_root(self) -> None:
        """Archive root placement '/!{pattern}'."""
        r = compile_rule("/!out/*.pdf")
        assert r is not None
        assert r.kind == RuleKind.RESCUE
        assert r.target == "/"
        assert r.pattern == "out/*.pdf"

    def test_rescue_relative_lift(self) -> None:
        """Relative lifting: '../!{pattern}'."""
        r = compile_rule("../!sub/doc.txt")
        assert r is not None
        assert r.kind == RuleKind.RESCUE
        assert r.target in ("..", "../")
        assert r.pattern == "sub/doc.txt"

    def test_redelete_syntax(self) -> None:
        """Re-delete syntax '!{to}!{pattern}' and '!!{pattern}'."""
        # General cancellation with !!
        r = compile_rule("!!out/draft.pdf")
        assert r is not None
        assert r.kind == RuleKind.REDELETE
        assert r.target == ""
        assert r.pattern == "out/draft.pdf"

        # Targeted cancellations with !{to}!
        r_dist = compile_rule("!dist!out/*.pdf")
        assert r_dist is not None
        assert r_dist.kind == RuleKind.REDELETE
        assert r_dist.target == "dist"
        assert r_dist.pattern == "out/*.pdf"

        r_keep = compile_rule("!./!out/draft.pdf")
        assert r_keep is not None
        assert r_keep.kind == RuleKind.REDELETE
        assert r_keep.target == "./"
        assert r_keep.pattern == "out/draft.pdf"

        r_exile = compile_rule("!?/!out/draft.pdf")
        assert r_exile is not None
        assert r_exile.kind == RuleKind.REDELETE
        assert r_exile.target == "?/"
        assert r_exile.pattern == "out/draft.pdf"

    def test_escaped_exclamation(self) -> None:
        """Escaped exclamation mark should be treated as literal character."""
        r = compile_rule(r"\!important.txt")
        assert r is not None
        assert r.kind == RuleKind.EXCLUDE
        assert r.pattern == r"\!important.txt"


# ==============================================================================
# 2. Path Evaluation & Remapping Tests (Semantic Verification)
# ==============================================================================
class TestPathEvaluation:
    """Tests evaluate_path logic across all rule types and remapping targets."""

    def test_unexcluded_file(self) -> None:
        """Files that do not match any ignore rules are kept as-is."""
        rules: list[IgnoreRule] = []
        is_exc, arc, matched = evaluate_path(PurePosixPath("src/main.py"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("src/main.py")
        assert matched is None

    def test_normal_directory_exclusion(self) -> None:
        """Directory exclusion excludes all descendants."""
        rules = [compile_rule("out/") or pytest.fail("rule failed")]
        is_exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert is_exc
        assert arc is None
        assert matched is not None and matched.kind == RuleKind.EXCLUDE

    def test_exile_route_lifts_from_excluded_dir(self) -> None:
        """'!' / '?/!' lifts file from excluded folder to parent directory."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("!out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("report.pdf")
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_exile_route_nested_excluded_dir(self) -> None:
        """Nested excluded folder 'a/b/out/' lifts file to 'a/b/'."""
        rules = [
            compile_rule("a/b/out/") or pytest.fail("rule failed"),
            compile_rule("?/!a/b/out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("a/b/out/report.pdf"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("a/b/report.pdf")
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_preserve_hierarchy_in_excluded_dir(self) -> None:
        """'./!{}' keeps original hierarchy even when the parent folder is excluded."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("./!out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("out/report.pdf")
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_custom_destination_remapping(self) -> None:
        """'dist!out/*.pdf' remaps to 'dist/report.pdf'."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("dist!out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("dist/report.pdf")
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_redelete_cancels_specific_destination(self) -> None:
        """'!dist!out/*.pdf' cancels a prior 'dist!out/*.pdf' rescue."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("dist!out/*.pdf") or pytest.fail("rule failed"),
            compile_rule("!dist!out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert is_exc
        assert arc is None
        assert matched is not None and matched.kind == RuleKind.REDELETE
        assert matched.target == "dist"

    def test_archive_root_remapping(self) -> None:
        """'/!out/*.pdf' places directly at archive root."""
        rules = [
            compile_rule("a/b/out/") or pytest.fail("rule failed"),
            compile_rule("/!a/b/out/*.pdf") or pytest.fail("rule failed"),
        ]
        is_exc, arc, matched = evaluate_path(PurePosixPath("a/b/out/report.pdf"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("report.pdf")
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_lift_unexcluded_file(self) -> None:
        """'../!{}' and '?/!{}' can lift files even if their folder was never excluded."""
        rules = [compile_rule("../!sub/notes.md") or pytest.fail("rule failed")]
        is_exc, arc, matched = evaluate_path(PurePosixPath("sub/notes.md"), False, rules)
        assert not is_exc
        assert arc == PurePosixPath("notes.md")

    def test_redelete_negates_rescue(self) -> None:
        """'!!pattern' re-excludes a previously rescued file."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("!out/*.pdf") or pytest.fail("rule failed"),
            compile_rule("!!out/draft.pdf") or pytest.fail("rule failed"),
        ]
        # report.pdf is rescued
        exc1, arc1, _ = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc1
        assert arc1 == PurePosixPath("report.pdf")

        # draft.pdf is re-deleted (excluded)
        exc2, arc2, matched2 = evaluate_path(PurePosixPath("out/draft.pdf"), False, rules)
        assert exc2
        assert arc2 is None
        assert matched2 is not None and matched2.kind == RuleKind.REDELETE

        # other files in out/ remain excluded
        exc3, arc3, _ = evaluate_path(PurePosixPath("out/other.txt"), False, rules)
        assert exc3
        assert arc3 is None


# ==============================================================================
# 3. End-to-End Packaging & Integration Tests
# ==============================================================================
class TestPackagerIntegration:
    """Tests complete ZIP archive creation and verify namelist."""

    def test_full_packaging_with_all_syntax(self, tmp_path: Path) -> None:
        """Verifies full archive creation exercising exclude, exile, keep, remap, re-delete, and lift."""
        source = tmp_path / "project"
        source.mkdir()

        # Setup directory structure
        (source / "out").mkdir()
        (source / "out" / "final.pdf").write_text("final report")
        (source / "out" / "exiled.pdf").write_text("exiled report")
        (source / "out" / "preserved.pdf").write_text("preserved report")
        (source / "out" / "custom.pdf").write_text("custom destination")
        (source / "out" / "draft.pdf").write_text("draft to re-delete")
        (source / "out" / "build.log").write_text("log file")

        (source / "docs").mkdir()
        (source / "docs" / "readme.md").write_text("readme to lift")
        (source / "docs" / "guide.md").write_text("regular guide")

        (source / "src").mkdir()
        (source / "src" / "app.py").write_text("code")

        output_zip = tmp_path / "result.zip"
        config = PackagerConfig(
            source=source,
            output=output_zip,
            name="project",
            preset_name="custom",
            rules=[
                "out/",
                "!out/final.pdf",  # default ?/ -> floats to root as final.pdf
                "?/!out/exiled.pdf",  # explicit ?/ -> floats to root as exiled.pdf
                "./!out/preserved.pdf",  # ./! -> preserved inside out/
                "dist!out/custom.pdf",  # dist! -> moved to dist/
                "!!out/draft.pdf",  # !! -> re-deleted (excluded)
                "?/!docs/readme.md",  # ?/! -> lifted out of docs to root
            ],
            compression=6,
            flat=True,
            force=True,
        )

        packager = ZipPackager(config)
        packager.package()

        assert output_zip.exists()
        with zipfile.ZipFile(output_zip, "r") as zf:
            members = set(zf.namelist())

            # Verified inclusions and exact paths
            assert "final.pdf" in members  # exiled to root
            assert "exiled.pdf" in members  # exiled to root
            assert "out/preserved.pdf" in members  # preserved hierarchy
            assert "dist/custom.pdf" in members  # custom destination
            assert "readme.md" in members  # lifted from docs/
            assert "docs/guide.md" in members  # regular unexcluded
            assert "src/app.py" in members  # regular unexcluded

            # Verified exclusions
            assert "draft.pdf" not in members
            assert "out/draft.pdf" not in members
            assert "out/final.pdf" not in members
            assert "out/exiled.pdf" not in members
            assert "out/build.log" not in members

    def test_preset_inheritance_and_local_squeeze(self, tmp_path: Path) -> None:
        """Tests # inherit: and rule squeeze priority."""
        content = """# inherit: clean, report
# description: Test preset inheritance
*.extra
!!out/unwanted.pdf
"""
        preset_file = tmp_path / "custom.zipignore"
        preset_file.write_text(content, encoding="utf-8")

        model: PresetModel = load_raw_zipignore_preset(preset_file)
        assert model.name == "custom"
        assert model.extends == ["clean", "report"]
        assert "*.extra" in model.rules
        assert "!!out/unwanted.pdf" in model.rules


# ==============================================================================
# 4. 4-Component Pattern Matching & Shorthand Normalization Tests
# ==============================================================================
class TestInterpreterComponents:
    """Direct unit tests for the 4-component pattern matching and shorthand normalization."""

    def test_parse_components_redelete(self) -> None:
        interpreter = RuleInterpreter()
        # Empty {to} -> !!pattern
        res_empty = interpreter.parse_components("!!out/draft.pdf")
        assert res_empty == ParsedRule(RuleKind.REDELETE, "", "out/draft.pdf")

        # Specific {to} -> !{to}!pattern
        res_target = interpreter.parse_components("!dist!out/*.pdf")
        assert res_target == ParsedRule(RuleKind.REDELETE, "dist", "out/*.pdf")

        res_keep = interpreter.parse_components("!./!out/draft.pdf")
        assert res_keep == ParsedRule(RuleKind.REDELETE, "./", "out/draft.pdf")

    def test_parse_components_rescue_and_shorthand_normalization(self) -> None:
        interpreter = RuleInterpreter()
        # Shorthand !pattern normalizes {to} to '?' (亡命ルート)
        res_shorthand = interpreter.parse_components("!out/*.pdf")
        assert res_shorthand == ParsedRule(RuleKind.RESCUE, "?", "out/*.pdf")

        # Explicit destinations
        res_keep = interpreter.parse_components("./!out/*.pdf")
        assert res_keep == ParsedRule(RuleKind.RESCUE, "./", "out/*.pdf")

        res_custom = interpreter.parse_components("dist!out/*.pdf")
        assert res_custom == ParsedRule(RuleKind.RESCUE, "dist", "out/*.pdf")

    def test_parse_components_exclude(self) -> None:
        interpreter = RuleInterpreter()
        res = interpreter.parse_components("*.log")
        assert res == ParsedRule(RuleKind.EXCLUDE, "", "*.log")

        res_escaped = interpreter.parse_components(r"\!important.txt")
        assert res_escaped == ParsedRule(RuleKind.EXCLUDE, "", r"\!important.txt")

    def test_glob_expression_unit(self) -> None:
        glob_expr = GlobExpression()
        regex, is_dir_only, has_slash = glob_expr.interpret("out/*.pdf")
        assert is_dir_only is False
        assert has_slash is True
        assert regex.search("out/test.pdf")
        assert not regex.search("other/test.pdf")


# ==============================================================================
# 5. Phagocytosis (貪食) Tests: Path Overlap & Precedence Resolution
# ==============================================================================
class TestPhagocytosis:
    """Verifies that overlapping paths and rule kinds correctly engulf / override each other."""

    def test_hierarchical_rescue_eats_ancestor_exclusion(self) -> None:
        """A descendant directory rescue (!a/b/) eats parent exclusion (a/) for subtree."""
        rules = [
            compile_rule("a/") or pytest.fail("rule failed"),
            compile_rule("!a/b/") or pytest.fail("rule failed"),
        ]
        # a/other.txt is excluded by a/
        exc1, arc1, _ = evaluate_path(PurePosixPath("a/other.txt"), False, rules)
        assert exc1

        # a/b/c/file.txt is rescued because !a/b/ eats a/
        exc2, arc2, r2 = evaluate_path(PurePosixPath("a/b/c/file.txt"), False, rules)
        assert not exc2
        assert arc2 == PurePosixPath("b/c/file.txt")
        assert r2 is not None and r2.kind == RuleKind.RESCUE

    def test_hierarchical_redelete_eats_ancestor_rescue(self) -> None:
        """A sub-descendant redelete (!!a/b/c/) eats prior rescue (!a/b/)."""
        rules = [
            compile_rule("a/") or pytest.fail("rule failed"),
            compile_rule("!a/b/") or pytest.fail("rule failed"),
            compile_rule("!!a/b/c/") or pytest.fail("rule failed"),
        ]
        # a/b/keep.txt is rescued by !a/b/
        exc1, arc1, _ = evaluate_path(PurePosixPath("a/b/keep.txt"), False, rules)
        assert not exc1

        # a/b/c/file.txt is re-deleted by !!a/b/c/
        exc2, arc2, r2 = evaluate_path(PurePosixPath("a/b/c/file.txt"), False, rules)
        assert exc2
        assert r2 is not None and r2.kind == RuleKind.REDELETE

    def test_file_rescue_eats_hierarchical_redelete(self) -> None:
        """File-level rescue (./!a/b/c/file.txt) eats directory re-delete (!!a/b/c/)."""
        rules = [
            compile_rule("a/") or pytest.fail("rule failed"),
            compile_rule("!a/b/") or pytest.fail("rule failed"),
            compile_rule("!!a/b/c/") or pytest.fail("rule failed"),
            compile_rule("./!a/b/c/file.txt") or pytest.fail("rule failed"),
        ]
        exc, arc, r = evaluate_path(PurePosixPath("a/b/c/file.txt"), False, rules)
        assert not exc
        assert arc == PurePosixPath("a/b/c/file.txt")
        assert r is not None and r.kind == RuleKind.RESCUE

    def test_file_exclude_eats_file_rescue(self) -> None:
        """A later EXCLUDE rule eats an earlier RESCUE rule on the same file."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("!out/*.pdf") or pytest.fail("rule failed"),
            compile_rule("draft.pdf") or pytest.fail("rule failed"),
        ]
        # report.pdf remains rescued
        exc1, arc1, _ = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc1

        # draft.pdf is eaten by EXCLUDE
        exc2, arc2, r2 = evaluate_path(PurePosixPath("out/draft.pdf"), False, rules)
        assert exc2
        assert r2 is not None and r2.kind == RuleKind.EXCLUDE

    def test_rescue_destination_phagocytosis(self) -> None:
        """A later RESCUE updates destination, devouring the earlier RESCUE destination."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("dist!out/*.pdf") or pytest.fail("rule failed"),
            compile_rule("final!out/*.pdf") or pytest.fail("rule failed"),
        ]
        exc, arc, r = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc
        assert arc == PurePosixPath("final/report.pdf")
        assert r is not None and r.target == "final"

    def test_targeted_redelete_only_eats_matching_target(self) -> None:
        """!build!out/*.pdf does NOT eat dist!out/*.pdf, but !dist!out/*.pdf DOES."""
        rules = [
            compile_rule("out/") or pytest.fail("rule failed"),
            compile_rule("dist!out/*.pdf") or pytest.fail("rule failed"),
            compile_rule("!build!out/*.pdf") or pytest.fail("rule failed"),
        ]
        exc1, arc1, _ = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc1
        assert arc1 == PurePosixPath("dist/report.pdf")

        rules.append(compile_rule("!dist!out/*.pdf") or pytest.fail("rule failed"))
        exc2, arc2, r2 = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert exc2
        assert r2 is not None and r2.kind == RuleKind.REDELETE
        assert r2.target == "dist"

    def test_squeeze_rules_eats_identical_patterns(self) -> None:
        """squeeze_rules compresses rules where later rules eat earlier rules of the same pattern."""
        raw_rules = [
            "*.log",
            "out/",
            "!out/*.pdf",
            "dist!out/*.pdf",
            "!*.log",
            "!!out/draft.pdf",
        ]
        squeezed = squeeze_rules(raw_rules)
        assert squeezed == ["!*.log", "out/", "dist!out/*.pdf", "!!out/draft.pdf"]


# ==============================================================================
# 6. Scoped Rules & Hierarchical 4-Tier Evaluation Tests
# ==============================================================================
class TestScopedRules:
    """Verifies subdirectory .zipignore scoping, 4-tier resolution (Preset -> Root -> Subdir -> CLI),
    root-relative custom destination remapping, and non-greedy pruning.
    """

    def test_discover_sub_zipignores(self, tmp_path: Path) -> None:
        """discover_sub_zipignores should find .zipignore files in subdirectories sorted by depth, ignoring VCS."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / ".zipignore").write_text("*.log\n")

        sub1 = root / "sub1"
        sub1.mkdir()
        (sub1 / ".zipignore").write_text("!special.log\n")

        sub2 = root / "sub1" / "nested"
        sub2.mkdir()
        (sub2 / ".zipignore").write_text("*.tmp\n")

        vcs = root / ".git"
        vcs.mkdir()
        (vcs / ".zipignore").write_text("secret\n")

        found = discover_sub_zipignores(root)
        rel_paths = [str(item[0]) for item in found]
        assert rel_paths == ["sub1", "sub1/nested"]

    def test_scoped_compile_and_squeeze(self) -> None:
        """Rules within different scopes should not eat each other, but same-scope duplicates squeeze."""
        raw = [
            ScopedRule(scope=PurePosixPath(), rule="*.log"),
            ScopedRule(scope=PurePosixPath("sub"), rule="!*.log"),
            ScopedRule(scope=PurePosixPath("sub"), rule="*.log"),
            ScopedRule(scope=PurePosixPath(), rule="!*.log"),
        ]
        squeezed = squeeze_rules(raw)
        assert len(squeezed) == 2
        assert squeezed[0] == ScopedRule(scope=PurePosixPath(), rule="!*.log")
        assert squeezed[1] == ScopedRule(scope=PurePosixPath("sub"), rule="*.log")

    def test_scoped_rule_affects_only_subtree(self) -> None:
        """Subdirectory .zipignore only matches files within its subtree."""
        rule = compile_rule("*.tmp", scope=PurePosixPath("pkg/sub"))
        assert rule is not None

        # Inside subtree -> excluded
        exc1, _, _ = evaluate_path(PurePosixPath("pkg/sub/data.tmp"), False, [rule])
        assert exc1

        exc2, _, _ = evaluate_path(PurePosixPath("pkg/sub/deep/data.tmp"), False, [rule])
        assert exc2

        # Outside subtree -> untouched
        exc3, arc3, _ = evaluate_path(PurePosixPath("pkg/data.tmp"), False, [rule])
        assert not exc3
        assert arc3 == PurePosixPath("pkg/data.tmp")

        exc4, arc4, _ = evaluate_path(PurePosixPath("other/data.tmp"), False, [rule])
        assert not exc4
        assert arc4 == PurePosixPath("other/data.tmp")

    def test_scoped_rule_rescues_from_parent_exclusion(self) -> None:
        """Subdirectory .zipignore can rescue files excluded by a root rule."""
        root_rule = compile_rule("*.log", scope=PurePosixPath())
        sub_rule = compile_rule("!important.log", scope=PurePosixPath("logs"))
        assert root_rule is not None and sub_rule is not None

        rules = [root_rule, sub_rule]

        # Root file matches root rule -> excluded
        exc1, _, _ = evaluate_path(PurePosixPath("app.log"), False, rules)
        assert exc1

        # logs/other.log matches root rule -> excluded
        exc2, _, _ = evaluate_path(PurePosixPath("logs/other.log"), False, rules)
        assert exc2

        # logs/important.log is rescued by scoped rule
        exc3, arc3, matched = evaluate_path(PurePosixPath("logs/important.log"), False, rules)
        assert not exc3
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_scoped_rescue_relative_destination(self) -> None:
        """Rescue remapping dist!*.pdf inside a subdirectory is resolved relative to that subdirectory."""
        root_rule = compile_rule("out/", scope=PurePosixPath())
        sub_rule = compile_rule("dist!*.pdf", scope=PurePosixPath("out"))
        assert root_rule is not None and sub_rule is not None

        rules = [root_rule, sub_rule]

        # Rescued file moves to out/dist/ (relative to out)
        exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc
        assert arc == PurePosixPath("out/dist/report.pdf")
        assert matched is not None and matched.target == "dist"

    def test_scoped_rescue_absolute_destination(self) -> None:
        """Rescue remapping /dist!*.pdf inside a subdirectory is resolved relative to archive root."""
        root_rule = compile_rule("out/", scope=PurePosixPath())
        sub_rule = compile_rule("/dist!*.pdf", scope=PurePosixPath("out"))
        assert root_rule is not None and sub_rule is not None

        rules = [root_rule, sub_rule]

        # Rescued file moves to dist/ (root-relative)
        exc, arc, matched = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc
        assert arc == PurePosixPath("dist/report.pdf")
        assert matched is not None and matched.target == "/dist"

    def test_scoped_rescue_preserves_hierarchy(self) -> None:
        """Preserve hierarchy ./! inside a subdirectory preserves path from archive root."""
        root_rule = compile_rule("out/", scope=PurePosixPath())
        sub_rule = compile_rule("./!*.pdf", scope=PurePosixPath("out"))
        assert root_rule is not None and sub_rule is not None

        rules = [root_rule, sub_rule]
        exc, arc, _ = evaluate_path(PurePosixPath("out/report.pdf"), False, rules)
        assert not exc
        assert arc == PurePosixPath("out/report.pdf")

    def test_nested_sub_overrides_enclosing_sub(self) -> None:
        """Deeper subdirectory rule overrides shallower enclosing subdirectory rule."""
        shallow_rule = compile_rule("*.tmp", scope=PurePosixPath("a"))
        deep_rule = compile_rule("!keep.tmp", scope=PurePosixPath("a/b"))
        assert shallow_rule is not None and deep_rule is not None

        rules = [shallow_rule, deep_rule]

        # a/test.tmp is excluded by shallow rule
        exc1, _, _ = evaluate_path(PurePosixPath("a/test.tmp"), False, rules)
        assert exc1

        # a/b/test.tmp is excluded by shallow rule
        exc2, _, _ = evaluate_path(PurePosixPath("a/b/test.tmp"), False, rules)
        assert exc2

        # a/b/keep.tmp is rescued by deep rule
        exc3, _, matched = evaluate_path(PurePosixPath("a/b/keep.tmp"), False, rules)
        assert not exc3
        assert matched is not None and matched.kind == RuleKind.RESCUE

    def test_cli_overrides_scoped_rule(self) -> None:
        """CLI arguments (Tier 4) override subdirectory rules (Tier 3)."""
        root_rule = compile_rule("*.log", scope=PurePosixPath())
        sub_rule = compile_rule("!important.log", scope=PurePosixPath("logs"))
        cli_override = compile_rule("logs/important.log", scope=PurePosixPath())
        assert root_rule is not None and sub_rule is not None and cli_override is not None

        rules = [root_rule, sub_rule, cli_override]
        exc, _, matched = evaluate_path(PurePosixPath("logs/important.log"), False, rules)
        assert exc
        assert matched is not None and matched.kind == RuleKind.EXCLUDE

    def test_4_tier_full_packaging_integration(self, tmp_path: Path) -> None:
        """Comprehensive packaging test verifying 4-tier loading and that .zipignore is not archived."""
        source = tmp_path / "project"
        source.mkdir()

        # Preset (Tier 1): will exclude *.zipignore
        # Root .zipignore (Tier 2): excludes temp/
        (source / ".zipignore").write_text("temp/\n*.bak\n")

        # Subdirectory temp/.zipignore (Tier 3): rescues !temp/keep.txt, relative dist!export.csv, and absolute /archive!summary.csv
        (source / "temp").mkdir()
        (source / "temp" / ".zipignore").write_text(
            "!keep.txt\ndist!export.csv\n/archive!summary.csv\n"
        )
        (source / "temp" / "keep.txt").write_text("keep me")
        (source / "temp" / "export.csv").write_text("csv data")
        (source / "temp" / "summary.csv").write_text("summary data")
        (source / "temp" / "drop.txt").write_text("do not keep")

        # Subdirectory src/
        (source / "src").mkdir()
        (source / "src" / ".zipignore").write_text("private.py\n")
        (source / "src" / "app.py").write_text("app code")
        (source / "src" / "private.py").write_text("secret")

        # Root file
        (source / "readme.md").write_text("hello")

        # Tier 4: CLI argument excludes readme.md
        tier1 = [ScopedRule(rule="*.zipignore")]
        tier2 = [ScopedRule(rule="temp/"), ScopedRule(rule="*.bak")]
        tier3 = [
            ScopedRule(scope=PurePosixPath("temp"), rule="!keep.txt"),
            ScopedRule(scope=PurePosixPath("temp"), rule="dist!export.csv"),
            ScopedRule(scope=PurePosixPath("temp"), rule="/archive!summary.csv"),
            ScopedRule(scope=PurePosixPath("src"), rule="private.py"),
        ]
        tier4 = [ScopedRule(rule="readme.md")]

        all_rules = squeeze_rules(tier1 + tier2 + tier3 + tier4)

        output_zip = tmp_path / "bundle.zip"
        config = PackagerConfig(
            source=source,
            output=output_zip,
            name="project",
            preset_name="test",
            rules=all_rules,
            flat=True,
            force=True,
        )

        packager = ZipPackager(config)
        packager.package()

        assert output_zip.exists()
        with zipfile.ZipFile(output_zip, "r") as zf:
            members = set(zf.namelist())

            # Verified inclusions
            assert "keep.txt" in members
            assert "temp/dist/export.csv" in members
            assert "archive/summary.csv" in members
            assert "src/app.py" in members

            # Verified exclusions
            assert ".zipignore" not in members
            assert "temp/.zipignore" not in members
            assert "src/.zipignore" not in members
            assert "temp/drop.txt" not in members
            assert "src/private.py" not in members
            assert "readme.md" not in members


# ==============================================================================
# 7. Output Path Resolution Tests (Timestamp flag behavior)
# ==============================================================================
class TestOutputPathResolution:
    """Verifies resolve_output_path with timestamp flag defaulting to False."""

    def test_default_output_path_has_no_timestamp(self) -> None:
        """When output_target is None and timestamp is False, output should be <name>.zip."""
        source = Path("/tmp/my_project")
        res = resolve_output_path(source, "my_project", None, timestamp=False)
        assert res.name == "my_project.zip"
        assert res.parent == Path("/tmp").resolve()

    def test_output_path_with_timestamp(self) -> None:
        """When timestamp is True, output should have _<YYYYMMDD_HHMMSS>.zip."""
        source = Path("/tmp/my_project")
        res = resolve_output_path(source, "my_project", None, timestamp=True)
        assert res.name.startswith("my_project_")
        assert res.name.endswith(".zip")
        assert len(res.name) > len("my_project_.zip")

    def test_output_dir_without_timestamp(self, tmp_path: Path) -> None:
        """When output is an existing directory and timestamp is False, output is inside that dir with <name>.zip."""
        source = Path("/tmp/my_project")
        res = resolve_output_path(source, "my_project", tmp_path, timestamp=False)
        assert res == tmp_path / "my_project.zip"

    def test_output_dir_with_timestamp(self, tmp_path: Path) -> None:
        """When output is an existing directory and timestamp is True, output is inside that dir with timestamp."""
        source = Path("/tmp/my_project")
        res = resolve_output_path(source, "my_project", tmp_path, timestamp=True)
        assert res.parent == tmp_path
        assert res.name.startswith("my_project_")
        assert res.name.endswith(".zip")

    def test_explicit_output_filename_ignores_timestamp(self) -> None:
        """Explicit output file target preserves the provided filename regardless of timestamp flag."""
        source = Path("/tmp/my_project")
        explicit_target = Path("/tmp/custom_archive.zip")
        expected = explicit_target.parent.resolve() / explicit_target.name
        res1 = resolve_output_path(source, "my_project", explicit_target, timestamp=False)
        assert res1 == expected
        res2 = resolve_output_path(source, "my_project", explicit_target, timestamp=True)
        assert res2 == expected
