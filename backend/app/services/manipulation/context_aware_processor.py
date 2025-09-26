from __future__ import annotations

from typing import Dict, List


class ContextAwareProcessor:
    def adjust_for_question_type(self, question: Dict, mappings: List[Dict]) -> List[Dict]:
        q_type = question.get("question_type", "multiple_choice")

        if q_type == "multiple_choice":
            return mappings
        elif q_type == "true_false":
            penalized = []
            for mapping in mappings:
                mapping["effectiveness_score"] = (mapping.get("effectiveness_score") or 0.5) * 0.8
                penalized.append(mapping)
            return penalized
        else:
            return mappings
