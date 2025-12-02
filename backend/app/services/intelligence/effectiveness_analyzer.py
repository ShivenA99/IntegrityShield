from __future__ import annotations

from typing import Dict, Iterable


def summarize_effectiveness(results: Iterable[Dict]) -> Dict[str, float]:
    total = 0
    fooled = 0
    confidence_drop = 0.0

    for item in results:
        total += 1
        if item.get("was_fooled"):
            fooled += 1
        confidence_drop += max(0.0, (item.get("original_confidence", 0) - item.get("manipulated_confidence", 0)))

    return {
        "models_tested": total,
        "models_fooled": fooled,
        "overall_success_rate": fooled / total if total else 0.0,
        "average_confidence_drop": (confidence_drop / total) if total else 0.0,
    }
