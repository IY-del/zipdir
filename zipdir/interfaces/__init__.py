"""Interfaces package aggregating per-domain D* contracts, I* nominal interfaces, and M* factories."""

from zipdir.interfaces.evaluator import (
    DEvaluationState,
    DPathEvaluator,
    DRemapContext,
    IPathEvaluator,
    IRemapStrategy,
    IRuleTransition,
    MPathEvaluator,
)
from zipdir.interfaces.glob import DGlobCompiler, IGlobCompiler, MGlobCompiler
from zipdir.interfaces.interpreter import (
    DRuleInterpreter,
    DRuleSqueezer,
    DSqueezeBuffer,
    IRuleInterpreter,
    IRuleSqueezer,
    ISqueezeStrategy,
    MRuleInterpreter,
    MRuleSqueezer,
)
from zipdir.interfaces.models import (
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
from zipdir.interfaces.output import (
    DOutputResolver,
    IOutputResolver,
    IOutputTargetStrategy,
    MOutputResolver,
)
from zipdir.interfaces.packager import (
    DPackager,
    IArchiveEntryWriter,
    IPackager,
    MPackager,
)
from zipdir.interfaces.presets import (
    DPresetCatalog,
    IPresetCatalog,
    MPresetCatalog,
)
from zipdir.interfaces.ui import DReporter, IReporter, MReporter

__all__ = [
    "DEvaluationResult",
    "DEvaluationState",
    "DGlobCompiler",
    "DIgnoreRule",
    "DOutputResolver",
    "DPackager",
    "DPackagerConfig",
    "DParsedRule",
    "DPathEvaluator",
    "DPreset",
    "DPresetCatalog",
    "DRemapContext",
    "DReporter",
    "DResolvedOutput",
    "DRuleInterpreter",
    "DRuleSqueezer",
    "DScopedRule",
    "DSqueezeBuffer",
    "IArchiveEntryWriter",
    "IGlobCompiler",
    "IOutputResolver",
    "IOutputTargetStrategy",
    "IPackager",
    "IPathEvaluator",
    "IPresetCatalog",
    "IRemapStrategy",
    "IReporter",
    "IRuleInterpreter",
    "IRuleSqueezer",
    "IRuleTransition",
    "ISqueezeStrategy",
    "MGlobCompiler",
    "MInterface",
    "MOutputResolver",
    "MPackager",
    "MPathEvaluator",
    "MPresetCatalog",
    "MReporter",
    "MRuleInterpreter",
    "MRuleSqueezer",
    "RuleKind",
]
