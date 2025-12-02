#!/usr/bin/env python3
"""Preview the auto-generate prompt for a specific run/question."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.pipeline.auto_mapping_strategy import (
    build_generation_prompt,
    build_index_reference,
    get_strategy,
)
from app.services.data_management.structured_data_manager import StructuredDataManager


def load_question(structured: dict, question_number: str) -> dict:
    questions = structured.get("questions", [])
    lookup = {str(q.get("question_number") or q.get("q_number")): q for q in questions}
    question = lookup.get(str(question_number))
    if not question:
        raise SystemExit(f"Question {question_number} not found in structured.json")
    return question


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="Pipeline run identifier")
    parser.add_argument("question_number", help="Question number within the run")
    parser.add_argument("--structured", dest="structured_path", default=None,
                        help="Optional explicit path to structured.json (defaults to run directory)")
    args = parser.parse_args()

    run_dir = Path("backend/data/pipeline_runs") / args.run_id
    structured_path = Path(args.structured_path) if args.structured_path else run_dir / "structured.json"
    if not structured_path.exists():
        raise SystemExit(f"Could not find structured.json at {structured_path}")

    structured = json.loads(structured_path.read_text())
    question = load_question(structured, args.question_number)
    manipulation = question.get("manipulation") or {}

    stem_text = question.get("stem_text") or question.get("original_text") or manipulation.get("stem_text") or ""
    options = question.get("options_data") or manipulation.get("options") or {}
    question_type = question.get("question_type") or manipulation.get("question_type") or "mcq_single"
    gold_answer = question.get("gold_answer") or manipulation.get("gold_answer")

    options_lines = []
    if isinstance(options, dict):
        for key, value in options.items():
            options_lines.append(f"{key}. {value}")
    options_block = "\n".join(options_lines)

    strategy = get_strategy(question_type)
    prompt = build_generation_prompt(
        stem_text=stem_text,
        question_type=question_type,
        gold_answer=gold_answer,
        options_block=options_block,
        strategy=strategy,
        index_reference=build_index_reference(stem_text),
    )

    print("=== AUTO-GENERATE PROMPT ===\n")
    print(prompt)


if __name__ == "__main__":
    main()
