from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if "FAIRTESTAI_PIPELINE_ROOT" not in os.environ:
    repo_root = Path(__file__).resolve().parents[2]
    default_root = repo_root / "backend" / "data" / "pipeline_runs"
    os.environ["FAIRTESTAI_PIPELINE_ROOT"] = str(default_root)

from app import create_app
from app.services.data_management.structured_data_manager import StructuredDataManager
from app.services.pipeline.auto_mapping_strategy import (
    build_generation_prompt,
    build_index_reference,
    generate_heuristic_mappings,
    get_strategy,
)


def main(run_id: str) -> None:
    app = create_app()
    with app.app_context():
        manager = StructuredDataManager()
        structured = manager.load(run_id)
        questions = structured.get("questions") or []
        ai_questions = {str(q.get("q_number") or q.get("question_number")): q for q in structured.get("ai_questions") or []}

    if not questions:
        print(f"No questions found for run {run_id}")
        return

    print(f"Previewing auto-generation prompts for run {run_id}\n")
    for idx, question in enumerate(questions, start=1):
        label = str(question.get("q_number") or question.get("question_number") or idx)
        enriched = ai_questions.get(label, {})
        stem_text = enriched.get("stem_text") or question.get("stem_text") or question.get("original_text") or ""
        options = enriched.get("options") or question.get("options") or {}
        question_type = question.get("question_type") or "mcq_single"
        gold_answer = question.get("gold_answer") or question.get("gold")

        strategy = get_strategy(question_type)
        options_block = "\n".join(f"{key}. {value}" for key, value in (options or {}).items())
        index_reference = build_index_reference(stem_text)
        prompt = build_generation_prompt(
            stem_text=stem_text,
            question_type=question_type,
            gold_answer=gold_answer,
            options_block=options_block,
            strategy=strategy,
            index_reference=index_reference,
        )
        fallback_mappings, method = generate_heuristic_mappings(stem_text, question_type, strategy)

        print(f"Question {label} ({question_type})")
        print("Prompt preview:")
        print(prompt)
        print("Fallback mappings (offline):")
        print(json.dumps({"strategy": method, "mappings": fallback_mappings}, indent=2))
        print("-" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backend/scripts/preview_mapping_prompts.py <run_id>")
        sys.exit(1)
    main(sys.argv[1])
