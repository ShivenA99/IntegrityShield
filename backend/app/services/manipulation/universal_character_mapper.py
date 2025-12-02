from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from .mapping_strategies import load_strategy_mapping


@dataclass
class MappingResult:
    strategy: str
    character_map: Dict[str, str]
    coverage: float


class UniversalCharacterMapper:
    """Generate character-level mappings for multiple strategies."""

    def create_mapping(self, strategy: str, *, custom_mapping: Dict[str, str] | None = None) -> MappingResult:
        if strategy == "custom" and custom_mapping is None:
            raise ValueError("custom mapping requires explicit character map")

        mapping = custom_mapping or load_strategy_mapping(strategy)
        coverage = len(mapping) / 95  # approximate ASCII coverage
        return MappingResult(strategy=strategy, character_map=mapping, coverage=min(1.0, coverage))

    def evaluate_coverage(self, text: str, character_map: Dict[str, str]) -> float:
        candidates: Iterable[str] = (char for char in text if char.strip())
        total = 0
        mapped = 0
        for char in candidates:
            total += 1
            if char in character_map:
                mapped += 1
        return (mapped / total) if total else 0.0
