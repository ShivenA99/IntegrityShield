from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable


def detect_patterns(results: Iterable[Dict]) -> Dict[str, Dict]:
    fooled_models = [result["model"] for result in results if result.get("was_fooled")]
    counter = Counter(fooled_models)
    return {
        "fooled_models": counter,
        "most_common_model": counter.most_common(1)[0][0] if counter else None,
    }
