from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable

from ...data_management.structured_data_manager import StructuredDataManager


class BaseRenderer(ABC):
    def __init__(self) -> None:
        self.structured_manager = StructuredDataManager()

    @abstractmethod
    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        """Generate an enhanced PDF and return metadata."""

    def build_mapping_from_questions(self, run_id: str) -> Dict[str, str]:
        structured = self.structured_manager.load(run_id)
        mapping: Dict[str, str] = {}
        for question in structured.get("questions", []):
            manipulation = question.get("manipulation", {})
            for entry in manipulation.get("substring_mappings", []):
                original = (entry.get("original") or "").strip()
                replacement = (entry.get("replacement") or "").strip()
                if original and replacement:
                    mapping[original] = replacement
        return mapping
