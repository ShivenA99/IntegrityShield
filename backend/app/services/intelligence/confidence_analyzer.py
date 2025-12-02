from __future__ import annotations

from typing import Dict, Iterable


def compute_confidence_metrics(results: Iterable[Dict]) -> Dict[str, float]:
    highest_drop = 0.0
    lowest_confidence = 1.0

    for result in results:
        drop = max(0.0, (result.get("original_confidence", 0) - result.get("manipulated_confidence", 0)))
        highest_drop = max(highest_drop, drop)
        lowest_confidence = min(lowest_confidence, result.get("manipulated_confidence", 1.0))

    return {
        "max_confidence_drop": round(highest_drop, 3),
        "lowest_manipulated_confidence": round(lowest_confidence, 3),
    }
