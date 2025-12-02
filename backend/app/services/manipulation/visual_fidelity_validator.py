from __future__ import annotations

from typing import Dict


class VisualFidelityValidator:
    def estimate_similarity(self, original: str, replacement: str) -> float:
        if not original:
            return 1.0
        matches = sum(1 for a, b in zip(original, replacement) if a.lower() == b.lower())
        return matches / len(original)

    def validate_mapping(self, mapping: Dict) -> Dict:
        similarity = self.estimate_similarity(mapping["original"], mapping["replacement"])
        mapping.setdefault("visual_similarity", round(similarity, 2))
        return mapping
