from __future__ import annotations

from typing import Dict, List, Tuple


def build_unified_mappings(entities_by_qnum: Dict[str, Dict[str, str]]) -> List[Tuple[str, str]]:
    """Return a list of (input_entity, output_entity) pairs for the whole document.

    - Removes duplicates while preserving order of first appearance
    - Only includes pairs with non-empty input_entity
    """
    seen = set()
    pairs: List[Tuple[str, str]] = []
    for qnum in sorted(entities_by_qnum.keys(), key=lambda s: str(s)):
        ent = entities_by_qnum[qnum] or {}
        inp = (ent.get("input_entity") or "").strip()
        out = (ent.get("output_entity") or "").strip()
        if not inp:
            continue
        key = (inp, out)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs 