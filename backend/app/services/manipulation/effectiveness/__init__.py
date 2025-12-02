from __future__ import annotations

from statistics import mean
from typing import Dict, List


def aggregate_effectiveness(mappings: List[Dict]) -> float:
    scores = [mapping.get("effectiveness_score", 0.6) for mapping in mappings]
    return mean(scores) if scores else 0.0
