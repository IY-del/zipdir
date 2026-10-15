"""Unit tests for D* data invariants, I* nominal interfaces (DIP/ISP/LSP), and Strategy/Bridge patterns."""

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

import pytest
from pydantic import ValidationError

from zipdir import (
    ArchiveRootRemapStrategy,
    ConsoleReporter,
    DEvaluationResult,
    DGlobCompiler,
    DIgnoreRule,
    DOutputResolver,
    DPackager,
    DPackagerConfig,
    DParsedRule,
    DPathEvaluator,
    DPreset,
    DPresetCatalog,
    DReporter,
    DResolvedOutput,
    DRuleInterpreter,
    DScopedRule,
    EvaluationResult,
    ExileRemapStrategy,
    GlobExpression,
    IGlobCompiler,
    IgnoreRule,
    IOutputResolver,
    IPackager,
    IPathEvaluator,
    IPresetCatalog,
    IRemapStrategy,
    IReporter,
    IRuleInterpreter,
    IRuleSqueezer,
    LocalScopeRemapStrategy,
    OutputResolver,
    OverwriteSqueezeStrategy,
    PackagerConfig,
    ParentClimbRemapStrategy,
    ParsedRule,
    PathEvaluator,
    PreserveHierarchyRemapStrategy,
    PresetCatalog,
    PresetModel,
    RemapContext,
    ResolvedOutput,
    RuleInterpreter,
    RuleKind,
    ScopedRule,
    TargetedRedeleteSqueezeStrategy,
    ZipPackager,
    compile_rule,
)


class TestDataModelInvariants:
    """Verifies D* data contracts and runtime class invariants."""

    def test_d_inheritance_hierarchy(self) -> None:
        assert issubclass(ParsedRule, DParsedRule)
        assert issubclass(IgnoreRule, DIgnoreRule)
        assert issubclass(IgnoreRule, DParsedRule)
        assert issubclass(EvaluationResult, DEvaluationResult)
        assert issubclass(ResolvedOutput, DResolvedOutput)
        assert issubclass(ScopedRule, DScopedRule)
        assert issubclass(PresetModel, DPreset)
        assert issubclass(PackagerConfig, DPackagerConfig)

    def test_parsed_rule_invariants(self) -> None:
        with pytest.raises(ValueError, match="pattern must be non-empty"):
            ParsedRule(RuleKind.EXCLUDE, "", "")
        with pytest.raises(ValueError, match=r"'\?' is prohibited"):
            ParsedRule(RuleKind.RESCUE, "?/dist", "*.pdf")

    def test_ignore_rule_invariants(self) -> None:
        base = compile_rule("*.pdf")
        assert base is not None
        with pytest.raises(ValueError, match="scope must be a relative path"):
            IgnoreRule(
                raw="*.pdf",
                kind=RuleKind.EXCLUDE,
                target="",
                pattern="*.pdf",
                regex=base.regex,
                is_dir_only=False,
                has_slash=False,
                scope=PurePosixPath("/abs/scope"),
            )

    def test_evaluation_result_invariants(self) -> None:
        with pytest.raises(ValueError, match="excluded path cannot have an arc_path"):
            EvaluationResult(True, PurePosixPath("a.txt"), None)
        with pytest.raises(ValueError, match="included path must have an arc_path"):
            EvaluationResult(False, None, None)

    def test_resolved_output_invariants(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="explicit .zip path cannot fall back"):
            ResolvedOutput(
                path=tmp_path / "out.zip",
                explicit_zip=True,
                stem="out",
                fell_back=True,
            )

    def test_packager_config_invariants(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError):
            PackagerConfig(
                source=tmp_path,
                output=tmp_path / "out.zip",
                name="",
                preset_name="clean",
            )
        with pytest.raises(ValidationError):
            PackagerConfig(
                source=tmp_path,
                output=tmp_path / "out.zip",
                name="proj",
                preset_name="clean",
                compression=10,
            )


class TestNominalInterfacesAndDIP:
    """Verifies I* nominal subtyping without abc.ABC and Bridge constructor injection."""

    def test_nominal_interface_subtyping(self) -> None:
        assert issubclass(GlobExpression, (IGlobCompiler, DGlobCompiler))
        assert issubclass(RuleInterpreter, (IRuleSqueezer, IRuleInterpreter, DRuleInterpreter))
        assert issubclass(PathEvaluator, (IPathEvaluator, DPathEvaluator))
        assert issubclass(OutputResolver, (IOutputResolver, DOutputResolver))
        assert issubclass(PresetCatalog, (IPresetCatalog, DPresetCatalog))
        assert issubclass(ConsoleReporter, (IReporter, DReporter))
        assert issubclass(ZipPackager, (IPackager, DPackager))

    def test_bridge_custom_reporter_injection(self, tmp_path: Path) -> None:
        class RecordingReporter(IReporter):
            def __init__(self) -> None:
                self.use_color = False
                self.dry_run_called = False
                self.recorded_entries: list[str] = []

            def print_presets(self, presets: Mapping[str, PresetModel]) -> None:
                pass

            def print_dry_run(
                self,
                config: PackagerConfig,
                entries: Sequence[tuple[Path, str]],
                rescued_files: Sequence[tuple[str, str]],
                excluded_files: Sequence[str],
            ) -> None:
                self.dry_run_called = True
                self.recorded_entries = [arc for _, arc in entries]

            def print_summary(
                self,
                config: PackagerConfig,
                output: Path,
                entries: Sequence[tuple[Path, str]],
                rescued_files: Sequence[tuple[str, str]],
                excluded_files: Sequence[str],
            ) -> None:
                pass

        src = tmp_path / "app"
        src.mkdir()
        (src / "hello.txt").write_text("hi")
        cfg = PackagerConfig(
            source=src,
            output=tmp_path / "app.zip",
            name="app",
            preset_name="clean",
            flat=True,
            dry_run=True,
        )
        reporter = RecordingReporter()
        packager = ZipPackager(cfg, reporter=reporter)
        packager.package()

        assert reporter.dry_run_called
        assert reporter.recorded_entries == ["hello.txt"]


class TestStrategyPatterns:
    """Verifies Strategy implementations for remapping, squeezing, and output classification."""

    def test_remap_strategies_unit(self) -> None:
        rule = compile_rule("/dist!out/a.pdf")
        assert rule is not None
        ctx = RemapContext(
            rel_path=PurePosixPath("out/a.pdf"),
            rescued_by=rule,
            shallowest_excluded_ancestor=PurePosixPath("out"),
            sub_path=PurePosixPath("a.pdf"),
            anchor_parent=PurePosixPath("."),
        )
        strat = ArchiveRootRemapStrategy()
        assert strat.matches("/dist")
        assert strat.remap(ctx) == PurePosixPath("dist/a.pdf")

        for s_cls in (
            PreserveHierarchyRemapStrategy,
            ArchiveRootRemapStrategy,
            LocalScopeRemapStrategy,
            ParentClimbRemapStrategy,
            ExileRemapStrategy,
        ):
            assert issubclass(s_cls, IRemapStrategy)

    def test_custom_remap_strategy_injection(self) -> None:
        class PrefixOverrideStrategy(IRemapStrategy):
            def matches(self, target: str) -> bool:
                return target == "custom_hook"

            def remap(self, ctx: RemapContext) -> PurePosixPath:
                return PurePosixPath("hooked") / ctx.sub_path

        evaluator = PathEvaluator(
            ["out/", "custom_hook!out/file.txt"],
            remap_strategies=(PrefixOverrideStrategy(),),
        )
        res = evaluator.evaluate(PurePosixPath("out/file.txt"))
        assert not res.is_excluded
        assert res.arc_path == PurePosixPath("hooked/file.txt")

    def test_squeeze_strategies_compile_all_consistency(self) -> None:
        interpreter = RuleInterpreter()
        raw_rules = ["out/", "!out/*.pdf", "dist!out/*.pdf", "!build!out/*.pdf"]
        compiled = interpreter.compile_all(raw_rules, squeeze=True)
        assert [r.raw for r in compiled] == ["out/", "dist!out/*.pdf", "!build!out/*.pdf"]
        assert isinstance(
            interpreter.squeeze_strategies[RuleKind.EXCLUDE], OverwriteSqueezeStrategy
        )
        assert isinstance(
            interpreter.squeeze_strategies[RuleKind.REDELETE], TargetedRedeleteSqueezeStrategy
        )
