from __future__ import annotations

import json
from typing import Dict, Any


def build_validation_prompt(payload: Dict[str, Any]) -> str:
    q_type = (payload.get("q_type") or "").strip().lower()
    is_long_form = q_type in {"long_answer", "short_answer", "comprehension_qa", "fill_blank"}

    if is_long_form:
        return (
            "You will validate a Code Glyph attack candidate for a long-form question by comparing visual vs parsed question answers.\n"
            "Return STRICT JSON only.\n\n"
            "PROCESS:\n"
            "1. Answer the VISUAL (original) question in ≤300 chars\n"
            "2. Apply the substitution: replace STEM[char_start:char_end] with parsed_entity to form PARSED question\n"
            "3. Answer the PARSED question in ≤300 chars\n"
            "4. Compare: flip_result = true if answers differ in meaning (materially different intent or requirements).\n"
            "5. Provide a ≤150-char comparison analysis.\n\n"
            f"Validation JSON (input):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Output JSON shape:\n"
            "{\n"
            "  \"visual_evaluation\": {\"answer_text\": \"...\", \"reasoning\": \"...\"},\n"
            "  \"parsed_evaluation\": {\"answer_text\": \"...\", \"reasoning\": \"...\"},\n"
            "  \"flip_result\": true,\n"
            "  \"comparison_analysis\": \"...\"\n"
            "}"
        )
    else:
        return (
            "You will validate a Code Glyph attack candidate by comparing visual vs parsed question answers.\n"
            "Return STRICT JSON only.\n\n"
            "VALIDATION PROCESS:\n"
            "1. Answer the VISUAL (original) question as shown\n"
            "2. Apply the glyph substitution: replace STEM[char_start:char_end] with parsed_entity to form PARSED question\n"
            "3. Answer the PARSED question\n"
            "4. Compare answers:\n"
            "   - flip_result = true IF parsed answer != visual answer AND parsed answer matches target_wrong\n"
            "   - For MCQ/TF: compare option letters exactly\n"
            "   - For other types: compare semantic meaning of answers\n"
            "5. If flip_result=false, propose up to 3 alternative candidates that WOULD create successful flips\n\n"
            f"Validation JSON (input):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Output JSON shape:\n"
            "{\n"
            "  \"visual_evaluation\": {\"answer_label\": \"A\", \"reasoning\": \"Original question asks about X, answer is A because...\"},\n"
            "  \"parsed_evaluation\": {\"answer_label\": \"C\", \"reasoning\": \"After substitution, question asks about Y, answer is C because...\"},\n"
            "  \"flip_result\": true,\n"
            "  \"comparison_analysis\": \"Visual answer A differs from parsed answer C. Parsed answer C matches target_wrong.\",\n"
            "  \"alternatives\": [\n"
            "    {\"visual_entity\": \"and\", \"parsed_entity\": \"or\", \"positions\": {\"char_start\":45,\"char_end\":48}, \"predicted_flip\": true, \"reason\": \"Logic operator change would flip meaning\"}\n"
            "  ]\n"
            "}"
        ) 