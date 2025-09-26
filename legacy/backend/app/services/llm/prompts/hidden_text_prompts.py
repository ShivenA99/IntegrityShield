from __future__ import annotations

import json
from typing import Dict, Any


def build_wrong_answer_generation_prompt(question: Dict[str, Any]) -> str:
    q_type = (question.get("q_type") or "").strip()
    payload = {
        "q_type": q_type,
        "stem_text": question.get("stem_text") or "",
        "options": question.get("options") or {},
        "matches": question.get("matches") or [],
        "blanks": question.get("blanks") or [],
    }
    return (
        "You are generating WRONG answers for adversarial exam testing. First infer the RIGHT answer, then output a WRONG answer with a concise wrong_reason. Return JSON only.\n\n"
        f"Question JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
        "Output schemas by q_type:\n"
        "- mcq_single: {\"right\": \"B\", \"wrong\": \"D\", \"wrong_reason\": \"...\"}\n"
        "- mcq_multi: {\"right\": [\"A\",\"C\"], \"wrong\": [\"A\",\"B\"], \"wrong_reason\": \"...\"}\n"
        "- true_false: {\"right\": \"True\", \"wrong\": \"False\", \"wrong_reason\": \"...\"}\n"
        "- match: {\"right\": [{\"L\":\"A\",\"R\":\"3\"},...], \"wrong\": [{\"L\":\"A\",\"R\":\"2\"},...], \"wrong_reason\": \"...\"}\n"
        "- fill_blank: {\"right\": \"token\", \"wrong\": \"token\", \"wrong_reason\": \"...\"}\n"
        "- short_answer/long_answer/comprehension_qa: {\"right\": \"text\", \"wrong\": \"text\", \"wrong_reason\": \"...\"}\n"
    ) 