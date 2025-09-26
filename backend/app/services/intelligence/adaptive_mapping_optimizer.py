from __future__ import annotations

from typing import Dict, List


def recommend_adjustments(results: Dict[str, Dict], mappings: List[Dict]) -> Dict:
    if not mappings:
        return {"recommendation": "Add mappings to increase manipulation coverage."}

    improved = sorted(mappings, key=lambda item: item.get("effectiveness_score", 0), reverse=True)
    return {
        "recommendation": "Focus on high-impact substrings",
        "top_suggestions": improved[:3],
    }
