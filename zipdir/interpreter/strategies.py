"""Concrete squeeze strategies and mutable buffer state for compile-time phagocytosis."""

from collections.abc import Sequence
from pathlib import PurePosixPath

from zipdir.interfaces.interpreter import DSqueezeBuffer, ISqueezeStrategy
from zipdir.interfaces.models import DParsedRule, RuleKind
from zipdir.models import redelete_matches_rescue


class SqueezeBuffer[T](DSqueezeBuffer[T]):
    """Concrete mutable buffer state for compile-time rule squeezing."""

    items: list[T]
    parsed_meta: list[DParsedRule]
    seen: dict[tuple[PurePosixPath, str], list[int]]

    def __init__(self) -> None:
        self.items = []
        self.parsed_meta = []
        self.seen = {}

    def shift_indices(self, removed_idx: int) -> None:
        """Adjust recorded index positions after an element removal."""
        for key, idx_list in self.seen.items():
            self.seen[key] = [i - 1 if i > removed_idx else i for i in idx_list if i != removed_idx]


class OverwriteSqueezeStrategy(ISqueezeStrategy):
    """Concrete Strategy for EXCLUDE and RESCUE: engulfs all prior rules sharing (scope, pattern)."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: DParsedRule,
        entry: T,
    ) -> None:
        primary_idx = indices[0]
        buffer.items[primary_idx] = entry
        buffer.parsed_meta[primary_idx] = parsed
        if len(indices) > 1:
            for drop_idx in sorted(indices[1:], reverse=True):
                del buffer.items[drop_idx]
                del buffer.parsed_meta[drop_idx]
                buffer.shift_indices(drop_idx)
            buffer.seen[key] = [buffer.seen[key][0]]


class TargetedRedeleteSqueezeStrategy(ISqueezeStrategy):
    """Concrete Strategy for REDELETE: replaces matching-target RESCUE/REDELETE or appends."""

    def apply[T](
        self,
        buffer: DSqueezeBuffer[T],
        key: tuple[PurePosixPath, str],
        indices: list[int],
        parsed: DParsedRule,
        entry: T,
    ) -> None:
        matched_idx = self._find_matching_index(parsed.target, indices, buffer.parsed_meta)
        if matched_idx is not None:
            buffer.items[matched_idx] = entry
            buffer.parsed_meta[matched_idx] = parsed
        else:
            indices.append(len(buffer.items))
            buffer.items.append(entry)
            buffer.parsed_meta.append(parsed)

    def _find_matching_index(
        self,
        redelete_target: str,
        indices: list[int],
        parsed_meta: Sequence[DParsedRule],
    ) -> int | None:
        for idx in reversed(indices):
            candidate = parsed_meta[idx]
            if candidate.kind in (RuleKind.RESCUE, RuleKind.REDELETE) and redelete_matches_rescue(
                redelete_target, candidate.target
            ):
                return idx
        return None


DEFAULT_SQUEEZE_STRATEGIES: dict[RuleKind, ISqueezeStrategy] = {
    RuleKind.EXCLUDE: OverwriteSqueezeStrategy(),
    RuleKind.RESCUE: OverwriteSqueezeStrategy(),
    RuleKind.REDELETE: TargetedRedeleteSqueezeStrategy(),
}
