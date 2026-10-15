"""Concrete squeeze strategies for compile-time rule squeezing."""

from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.interpreter import ISqueezeStrategy, SqueezeBuffer
from zipdir.models import ParsedRule, RuleKind, redelete_matches_rescue


class OverwriteSqueezeStrategy(ISqueezeStrategy):
    """Strategy for EXCLUDE and RESCUE: overwrites prior rules sharing (scope, pattern)."""

    def apply[T](
        self,
        buffer: SqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: ParsedRule,
        entry: T,
    ) -> None:
        primary_idx = indices[0]
        buffer.items[primary_idx] = entry
        buffer.parsed_meta[primary_idx] = parsed
        match len(indices):
            case count if count > 1:
                for drop_idx in sorted(indices[1:], reverse=True):
                    del buffer.items[drop_idx]
                    del buffer.parsed_meta[drop_idx]
                    buffer.shift_indices(drop_idx)
                buffer.seen[key] = [buffer.seen[key][0]]
            case _:
                pass


class TargetedRedeleteSqueezeStrategy(ISqueezeStrategy):
    """Strategy for REDELETE: replaces matching-target RESCUE/REDELETE or appends."""

    def apply[T](
        self,
        buffer: SqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: ParsedRule,
        entry: T,
    ) -> None:
        matched_idx = self._find_matching_index(parsed.target, indices, buffer.parsed_meta)
        match matched_idx:
            case int() as idx:
                buffer.items[idx] = entry
                buffer.parsed_meta[idx] = parsed
            case None:
                indices.append(len(buffer.items))
                buffer.items.append(entry)
                buffer.parsed_meta.append(parsed)

    def _find_matching_index(
        self,
        redelete_target: str,
        indices: list[int],
        parsed_meta: Sequence[ParsedRule],
    ) -> int | None:
        for idx in reversed(indices):
            candidate = parsed_meta[idx]
            match candidate.kind:
                case RuleKind.RESCUE | RuleKind.REDELETE if redelete_matches_rescue(
                    redelete_target, candidate.target
                ):
                    return idx
                case _:
                    continue
        return None


DEFAULT_SQUEEZE_STRATEGIES: dict[RuleKind, ISqueezeStrategy] = {
    RuleKind.EXCLUDE: OverwriteSqueezeStrategy(),
    RuleKind.RESCUE: OverwriteSqueezeStrategy(),
    RuleKind.REDELETE: TargetedRedeleteSqueezeStrategy(),
}
