#!/usr/bin/env python3
"""Prototype: ask GPT-5 to refine substring span alignment for a question.

Usage:
    PYTHONPATH=backend backend/.venv/bin/python3.13 tools/test_span_alignment.py \
        --run-id 71a85e78-7d88-4f5f-b675-1ce6d292b693 --question 5

The script loads structured data and span metadata for the requested run, prepares
the candidate spans on the relevant page, renders a page snapshot, and then calls
``GPT5FusionClient.suggest_span_alignment`` with that context. The response is
printed to stdout so we can inspect whether GPT-5 proposes usable span IDs.

The call requires an OpenAI API key configured in the environment or Flask config.
When no provider is configured, the helper returns a simulated payload.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List

import fitz

from app import create_app
from app.services.ai_clients.gpt5_fusion_client import GPT5FusionClient
from app.services.pipeline.enhancement_methods.base_renderer import BaseRenderer
from app.services.pipeline.enhancement_methods.span_extractor import collect_span_records


def _collect_page_spans(page: fitz.Page) -> List[Dict[str, Any]]:
    records = collect_span_records(page, int(page.number))
    spans: List[Dict[str, Any]] = []
    for record in records:
        bbox = getattr(record, "bbox", None)
        if bbox:
            bbox_values = [float(value) for value in bbox]
        else:
            bbox_values = None
        raw_text = getattr(record, "text", "") or ""
        normalized = getattr(record, "normalized_text", "") or raw_text
        if len(raw_text) > 60:
            raw_text = raw_text[:57] + "..."
        if len(normalized) > 60:
            normalized = normalized[:57] + "..."
        spans.append(
            {
                "span_id": f"page{page.number}:block{record.block_index}:line{record.line_index}:span{record.span_index}",
                "text": raw_text,
                "normalized_text": normalized,
                "bbox": bbox_values,
            }
        )
    return spans


def _resolve_question(run_id: str, q_number: str, renderer: BaseRenderer) -> Dict[str, Any]:
    structured = renderer.structured_manager.load(run_id) or {}
    questions = structured.get("questions") or []
    for entry in questions:
        if str(entry.get("q_number") or entry.get("question_number") or "").strip() == q_number:
            return entry
    raise ValueError(f"Question {q_number} not found in structured data")


def _resolve_mapping_context(run_id: str, q_number: str, renderer: BaseRenderer) -> Dict[str, Any]:
    mapping_context = renderer.build_mapping_context(run_id)
    for entries in mapping_context.values():
        for ctx in entries:
            if str(ctx.get("q_number") or "").strip() == q_number:
                return ctx
    raise ValueError(f"Mapping context for question {q_number} not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test GPT-5 span alignment helper")
    parser.add_argument("--run-id", required=True, help="Pipeline run ID")
    parser.add_argument("--question", required=True, help="Question number to inspect")
    parser.add_argument("--mapping-index", type=int, default=0, help="Index of the substring mapping to test")
    args = parser.parse_args()

    app = create_app("development")

    with app.app_context():
        renderer = BaseRenderer()
        question_entry = _resolve_question(args.run_id, args.question, renderer)
        mapping_ctx = _resolve_mapping_context(args.run_id, args.question, renderer)

        substrings = (question_entry.get("manipulation") or {}).get("substring_mappings") or []
        if not substrings:
            raise ValueError(f"Question {args.question} has no substring mappings")
        if args.mapping_index < 0 or args.mapping_index >= len(substrings):
            raise ValueError(
                f"mapping_index {args.mapping_index} out of range (0..{len(substrings)-1})"
            )
        mapping_entry = substrings[args.mapping_index]

        structured = renderer.structured_manager.load(args.run_id) or {}
        pdf_path = structured.get("document", {}).get("source_path")
        if not pdf_path:
            raise ValueError("Structured data missing document source path")

        doc = fitz.open(pdf_path)
        page_index = int(mapping_entry.get("selection_page") or mapping_ctx.get("page") or 0)
        page = doc[page_index]

        spans = _collect_page_spans(page)
        bbox_source = mapping_entry.get("selection_bbox") or mapping_ctx.get("selection_bbox")
        candidate_rect = None
        if bbox_source and len(bbox_source) == 4:
            try:
                candidate_rect = fitz.Rect(*bbox_source)
            except Exception:
                candidate_rect = None

        if candidate_rect is not None:
            expanded_rect = fitz.Rect(candidate_rect)
            expanded_rect.x0 -= 30
            expanded_rect.y0 -= 40
            expanded_rect.x1 += 30
            expanded_rect.y1 += 40

            filtered: List[Dict[str, Any]] = []
            for span in spans:
                bbox = span.get("bbox")
                if not bbox or len(bbox) != 4:
                    continue
                try:
                    span_rect = fitz.Rect(*bbox)
                except Exception:
                    continue
                if span_rect.intersects(expanded_rect):
                    filtered.append(span)
            if filtered:
                spans = filtered

        spans = spans[:60]
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1))
        page_image = None

        gpt_client = GPT5FusionClient()
        payload = {
            "original": mapping_entry.get("original"),
            "replacement": mapping_entry.get("replacement"),
            "prefix": mapping_ctx.get("prefix"),
            "suffix": mapping_ctx.get("suffix"),
            "occurrence_index": mapping_ctx.get("occurrence_index"),
        }

        result = gpt_client.suggest_span_alignment(
            question_number=str(args.question),
            mapping=payload,
            span_candidates=spans,
            page_image=page_image,
            run_id=args.run_id,
        )

        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
