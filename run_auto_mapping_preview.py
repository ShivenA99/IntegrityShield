#!/usr/bin/env python3
"""Call GPT-5 for auto-mapping on a given run/question and dump the prompt + response."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app import create_app
from app.services.integration.external_api_client import ExternalAIClient
from app.services.pipeline.auto_mapping_strategy import (
    build_generation_prompt,
    build_index_reference,
    get_strategy,
)


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
    parser.add_argument("--output", default="auto_mapping_preview.json", help="Output JSON file to save the response")
    args = parser.parse_args()

    run_dir = Path("backend/data/pipeline_runs") / args.run_id
    structured_path = run_dir / "structured.json"
    if not structured_path.exists():
        raise SystemExit(f"Could not find structured.json at {structured_path}")

    structured = json.loads(structured_path.read_text())
    question = load_question(structured, args.question_number)
    manipulation = question.get("manipulation") or {}

    stem_text = question.get("stem_text") or question.get("original_text") or manipulation.get("stem_text") or ""
    if not stem_text:
        raise SystemExit("Stem text is empty; cannot build prompt")

    options = question.get("options_data") or manipulation.get("options") or {}
    question_type = question.get("question_type") or manipulation.get("question_type") or "mcq_single"
    gold_answer = question.get("gold_answer") or manipulation.get("gold_answer")

    options_block = "\n".join(f"{k}. {v}" for k, v in options.items())

    strategy = get_strategy(question_type)
    prompt = build_generation_prompt(
        stem_text=stem_text,
        question_type=question_type,
        gold_answer=gold_answer,
        options_block=options_block,
        strategy=strategy,
        index_reference=build_index_reference(stem_text),
    )

    app = create_app()
    with app.app_context():
        client = ExternalAIClient()
        result = client.call_model(
            provider="openai:fusion",
            payload={
                "prompt": prompt,
                "response_format": {"type": "json_object"},
            },
        )

    output = {
        "prompt": prompt,
        "response": result,
    }
    Path(args.output).write_text(json.dumps(output, indent=2))
    print(f"Saved response to {args.output}")


if __name__ == "__main__":
    main()
