from __future__ import annotations

import base64
import copy
import json
import os
import time
from typing import Dict, Any, Optional, List, Tuple

from .base_ai_client import BaseAIClient, AIExtractionResult
from ..integration.external_api_client import ExternalAIClient
from ...utils.logging import get_logger


class GPT5FusionClient(BaseAIClient):
    """GPT-5 client for intelligent fusion of multiple data sources."""

    _MAX_SPANS_PER_PAGE = 120
    _MAX_TOTAL_SPANS = 600
    _MAX_SPAN_TEXT_CHARS = 80

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key or os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("GPT5_FUSION_MODEL", "gpt-5")
        self.logger = get_logger(__name__)
        self.ai_client = ExternalAIClient()

    def is_configured(self) -> bool:
        try:
            return self.ai_client.is_configured()
        except Exception:
            return False

    def analyze_elements_for_questions(self, content_elements: List[Dict], run_id: str) -> AIExtractionResult:
        """Analyze PyMuPDF content elements to identify questions and generate substring-level mappings."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error="GPT-5 fusion not configured - missing OpenAI API key"
            )

        try:
            # Filter text elements and sort by position
            text_elements = [elem for elem in content_elements if elem.get("type") == "text"]
            text_elements.sort(key=lambda e: (e.get("bbox", [0, 0])[1], e.get("bbox", [0, 0])[0]))

            # Create analysis prompt
            prompt = self._create_question_analysis_prompt(text_elements)
            payload = {
                "prompt": prompt,
                "response_format": {"type": "json_object"},
                "generation_options": {
                    "max_completion_tokens": 4000,
                    "max_output_tokens": 4000,
                },
            }

            call_result = self.ai_client.call_model("openai:fusion", payload)
            content = str(call_result.get("response") or "").strip()
            if not content:
                finish_reason = self._extract_finish_reason(call_result)
                raise RuntimeError(
                    "gpt5_fusion_empty_response"
                    + (f" (finish_reason={finish_reason})" if finish_reason else "")
                )
            processing_time = int((time.perf_counter() - start_time) * 1000)

            # Parse questions with manipulation targets
            questions = self._parse_question_analysis_response(content)
            confidence = 0.95 if questions else 0.1

            cost_cents = self._estimate_cost(len(prompt), len(content))
            self.logger.info(
                "GPT-5 question analysis found %d questions with manipulation targets",
                len(questions),
                run_id=run_id,
            )

            raw_response = call_result.get("raw_response")
            if not isinstance(raw_response, dict):
                raw_response = {
                    "content": content,
                    "model": call_result.get("provider", f"openai:{self.model}").split(":", 1)[-1],
                }

            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=confidence,
                questions=questions,
                raw_response=raw_response,
                processing_time_ms=processing_time,
                cost_cents=cost_cents
            )

        except Exception as e:
            self.logger.error(f"GPT-5 question analysis failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def extract_questions_from_pdf(self, pdf_path, run_id: str) -> AIExtractionResult:
        """Not implemented - GPT-5 fusion works with pre-extracted data."""
        raise NotImplementedError("GPT-5 fusion works with already extracted data from other sources")

    def extract_questions_from_page(self, page_image: bytes, page_number: int, run_id: str) -> AIExtractionResult:
        """Not implemented - GPT-5 fusion works with pre-extracted data."""
        raise NotImplementedError("GPT-5 fusion works with already extracted data from other sources")

    def fuse_extraction_results(
        self,
        pymupdf_data: Dict[str, Any],
        openai_vision_result: AIExtractionResult,
        mistral_ocr_result: AIExtractionResult,
        run_id: str
    ) -> AIExtractionResult:
        """Intelligently merge results from all three sources using GPT-5."""
        start_time = time.perf_counter()

        if not self.is_configured():
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error="GPT-5 fusion not configured - missing OpenAI API key"
            )

        try:
            vision_questions = self._normalize_vision_questions(openai_vision_result.questions)
            if not vision_questions:
                self.logger.warning("No Vision questions available for fusion", run_id=run_id)
                return AIExtractionResult(
                    source="gpt5_fusion",
                    confidence=0.0,
                    questions=[],
                    error="vision_questions_missing",
                )

            spans_by_page = self._index_span_records(pymupdf_data)
            questions_by_page = self._group_questions_by_page(vision_questions)

            geometry_by_question: Dict[str, Dict[str, Any]] = {}
            warnings: List[str] = []
            raw_calls: List[Dict[str, Any]] = []
            total_prompt_chars = 0
            total_completion_chars = 0
            total_spans_used = 0

            for page_number, page_questions in questions_by_page.items():
                span_entry = spans_by_page.get(page_number)
                if not span_entry:
                    warnings.append(f"page {page_number}: no span data available")
                    continue

                for question in page_questions:
                    q_number_raw = (
                        question.get("question_number")
                        or question.get("q_number")
                    )
                    if q_number_raw is None:
                        warnings.append(
                            f"page {page_number}: question missing number, skipping"
                        )
                        continue
                    q_number = str(q_number_raw).strip()

                    span_window, span_warnings = self._collect_question_spans(
                        span_entry,
                        question,
                    )
                    if not span_window:
                        warnings.append(
                            f"question {q_number}: span window empty"
                        )
                        warnings.extend(
                            [f"question {q_number}: {msg}" for msg in span_warnings]
                        )
                        continue
                    warnings.extend(
                        [f"question {q_number}: {msg}" for msg in span_warnings]
                    )

                    if total_spans_used + len(span_window) > self._MAX_TOTAL_SPANS:
                        warnings.append(
                            f"question {q_number}: skipped (span budget exceeded)"
                        )
                        continue
                    total_spans_used += len(span_window)

                    prompt = self._build_page_prompt(
                        page_number,
                        [
                            {
                                "question_number": q_number,
                                "stem_text": question.get("stem_text"),
                                "question_id": question.get("question_id"),
                                "approx_bbox": (question.get("positioning") or {}).get("bbox"),
                            }
                        ],
                        span_window,
                    )
                    payload = {
                        "prompt": prompt,
                        "response_format": {"type": "json_object"},
                        "generation_options": {
                            "max_completion_tokens": 5000,
                            "max_output_tokens": 5000,
                        },
                    }

                    call_result = self.ai_client.call_model("openai:fusion", payload)
                    raw_calls.append(call_result)
                    content = str(call_result.get("response") or "").strip()
                    if not content:
                        finish_reason = self._extract_finish_reason(call_result)
                        warnings.append(
                            f"question {q_number}: empty response (finish_reason={finish_reason})"
                        )
                        continue

                    geometry_map, page_warnings = self._parse_page_geometry_response(content)
                    geometry = geometry_map.get(q_number)
                    if geometry:
                        geometry_by_question[q_number] = geometry
                    else:
                        warnings.append(
                            f"question {q_number}: geometry missing in GPT response"
                        )
                    warnings.extend(
                        [f"question {q_number}: {w}" for w in page_warnings]
                    )

                    total_prompt_chars += len(prompt)
                    total_completion_chars += len(content)

            fused_questions = self._merge_geometry_with_vision(
                vision_questions,
                geometry_by_question,
                warnings,
            )

            confidence = self._calculate_fusion_confidence(
                fused_questions,
                openai_vision_result,
                mistral_ocr_result,
            )

            processing_time = int((time.perf_counter() - start_time) * 1000)
            cost_cents = self._estimate_cost(total_prompt_chars, total_completion_chars)

            self.logger.info(
                "GPT-5 page geometry enrichment complete",
                run_id=run_id,
                fused_count=len(fused_questions),
                warnings=len(warnings),
            )

            raw_payload = {
                "content": None,
                "calls": raw_calls,
                "warnings": warnings,
                "sources_used": ["pymupdf", "openai_vision", "mistral_ocr"],
            }

            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=confidence,
                questions=fused_questions,
                raw_response=raw_payload,
                processing_time_ms=processing_time,
                cost_cents=cost_cents,
            )

        except Exception as e:
            self.logger.error(f"GPT-5 fusion failed: {e}", run_id=run_id, error=str(e))
            return AIExtractionResult(
                source="gpt5_fusion",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def _build_page_prompt(
        self,
        page_number: int,
        vision_questions: List[Dict[str, Any]],
        span_summaries: List[Dict[str, Any]],
    ) -> str:
        payload = {
            "page": page_number,
            "vision_questions": vision_questions,
            "span_snippets": span_summaries,
        }

        instructions = {
            "task": "Map each Vision question to the PyMuPDF spans that compose its stem and return the unioned bounding box.",
            "rules": [
                "Use the Vision stem text exactly as-is; do not rewrite the text.",
                "Match spans by comparing the provided start/end snippets and overall length.",
                "Return spans in reading order (top-to-bottom, left-to-right).",
                "Compute the union bbox by merging the individual span boxes.",
                "If no spans match, return an empty list and add a warning explaining why.",
                "Return only valid JSON matching the specified output format; no extra commentary.",
            ],
            "output_format": {
                "geometry": [
                    {
                        "question_number": "string",
                        "stem_spans": ["string"],
                        "stem_bbox": [0, 0, 0, 0]
                    }
                ],
                "warnings": ["string"],
            },
        }

        prompt = {
            "instructions": instructions,
            "input": payload,
        }

        return json.dumps(prompt, indent=2)

    def _parse_page_geometry_response(
        self,
        content: str,
    ) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
        content = (content or "").strip()
        if not content:
            return {}, []
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            self.logger.warning("GPT-5 page geometry JSON decode failed: %s", exc)
            return {}, [f"json_parse_error: {exc}"]

        geometries = parsed.get("geometry") if isinstance(parsed, dict) else None
        warnings = parsed.get("warnings") if isinstance(parsed, dict) else None

        geometry_by_question: Dict[str, Dict[str, Any]] = {}
        if isinstance(geometries, list):
            for entry in geometries:
                if not isinstance(entry, dict):
                    continue
                q_number = str(entry.get("question_number") or "").strip()
                if not q_number:
                    continue
                spans = entry.get("stem_spans")
                if isinstance(spans, list):
                    span_ids = [str(span_id) for span_id in spans if span_id]
                elif isinstance(spans, str):
                    span_ids = [spans]
                else:
                    span_ids = []

                bbox = entry.get("stem_bbox")
                bbox_values: Optional[List[float]] = None
                if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                    try:
                        bbox_values = [float(bbox[i]) for i in range(4)]
                    except (TypeError, ValueError):
                        bbox_values = None

                geometry_by_question[q_number] = {
                    "stem_spans": span_ids,
                    "stem_bbox": bbox_values,
                }

        warning_messages: List[str] = []
        if isinstance(warnings, list):
            warning_messages = [str(msg) for msg in warnings if msg]

        return geometry_by_question, warning_messages

    def suggest_span_alignment(
        self,
        question_number: str,
        mapping: Dict[str, Any],
        span_candidates: List[Dict[str, Any]],
        page_image: Optional[bytes],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Ask GPT-5 to choose span IDs that cover a mapping's original text.

        Parameters
        ----------
        question_number: str
            The question identifier (e.g. "5").
        mapping: Dict[str, Any]
            Dict with keys: original, replacement, prefix, suffix, occurrence_index, etc.
        span_candidates: List[Dict[str, Any]]
            Each item should include ``span_id``, ``text`` (raw), ``normalized_text`` (optional), and ``bbox`` (tuple of four floats).
        page_image: Optional[bytes]
            PNG image bytes for the page (optional but improves accuracy when using vision-enabled models).
        """

        if not self.is_configured():
            return {
                "status": "not_configured",
                "span_ids": [],
                "confidence": 0.0,
                "reason": "AI provider not configured",
            }

        try:
            prompt = self._build_span_alignment_prompt(
                question_number,
                mapping,
                span_candidates,
                page_image,
            )

            payload = {
                "prompt": prompt,
                "generation_options": {
                    "max_completion_tokens": 1200,
                    "max_output_tokens": 1200,
                },
            }

            call_result = self.ai_client.call_model("openai:fusion", payload)
            content = str(call_result.get("response") or "").strip()
            parsed = self._parse_span_alignment_response(content)
            parsed.setdefault("raw_response", call_result)
            return parsed
        except Exception as exc:
            self.logger.error(
                "GPT-5 span alignment failed: %s",
                exc,
                run_id=run_id,
                question_number=question_number,
                error=str(exc),
            )
            return {
                "status": "error",
                "span_ids": [],
                "confidence": 0.0,
                "reason": str(exc),
            }

    def _build_span_alignment_prompt(
        self,
        question_number: str,
        mapping: Dict[str, Any],
        span_candidates: List[Dict[str, Any]],
        page_image: Optional[bytes],
    ) -> str:
        question_payload = {
            "question_number": question_number,
            "original": mapping.get("original"),
            "replacement": mapping.get("replacement"),
            "prefix": mapping.get("prefix"),
            "suffix": mapping.get("suffix"),
            "occurrence_index": mapping.get("occurrence_index"),
        }

        spans_serialized: List[Dict[str, Any]] = []
        for span in span_candidates[:60]:
            span_id = span.get("span_id") or span.get("id")
            if not span_id:
                continue
            spans_serialized.append(
                {
                    "span_id": span_id,
                    "text": span.get("text") or span.get("normalized_text") or "",
                    "normalized_text": span.get("normalized_text") or span.get("text") or "",
                    "bbox": span.get("bbox"),
                }
            )

        page_image_b64 = None
        if page_image:
            try:
                page_image_b64 = base64.b64encode(page_image).decode("ascii")
            except Exception:
                page_image_b64 = None

        instructions = {
            "task": "Select the spans that exactly cover the mapping's original text on the PDF page.",
            "steps": [
                "Only choose spans when the glyphs visibly match the original substring.",
                "You may combine adjacent spans if the text is split across multiple fragments.",
                "Prefer the minimal set of spans that fully covers the original text.",
                "Return an empty span list with a warning if the text is not present.",
                "Provide a short explanation describing how the spans were chosen.",
            ],
            "output_format": {
                "status": "success | warning | failure",
                "span_ids": ["span-id"],
                "confidence": "number between 0 and 1",
                "reason": "string explanation",
                "warnings": ["string"],
            },
        }

        payload: Dict[str, Any] = {
            "question": question_payload,
            "candidate_spans": spans_serialized,
        }
        if page_image_b64:
            payload["page_image_base64"] = page_image_b64

        prompt = {
            "instructions": instructions,
            "input": payload,
        }

        return json.dumps(prompt, indent=2)

    def _parse_span_alignment_response(self, content: str) -> Dict[str, Any]:
        content = (content or "").strip()
        if not content:
            return {
                "status": "empty",
                "span_ids": [],
                "confidence": 0.0,
                "reason": "Empty response",
            }
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            return {
                "status": "parse_error",
                "span_ids": [],
                "confidence": 0.0,
                "reason": f"json_decode_failed: {exc}",
            }

        span_ids = []
        if isinstance(parsed.get("span_ids"), list):
            span_ids = [str(item) for item in parsed["span_ids"] if item]

        return {
            "status": str(parsed.get("status") or "unknown"),
            "span_ids": span_ids,
            "confidence": float(parsed.get("confidence") or 0.0),
            "reason": str(parsed.get("reason") or ""),
            "warnings": parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else [],
        }

    def _prepare_span_prompt_inventory(self, pymupdf_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Prepare succinct span metadata for prompting."""

        span_index = (
            pymupdf_data.get("span_index")
            or pymupdf_data.get("pymupdf_span_index")
            or []
        )

        inventory: List[Dict[str, Any]] = []

        total_spans = 0
        for page_idx, page_entry in enumerate(span_index):
            if not isinstance(page_entry, dict):
                continue

            spans_raw = page_entry.get("spans")
            spans_list = spans_raw if isinstance(spans_raw, list) else []
            spans_summary: List[Dict[str, Any]] = []

            for span in spans_list:
                if total_spans >= self._MAX_TOTAL_SPANS:
                    break
                if not isinstance(span, dict):
                    continue

                span_id = span.get("id")
                if not span_id:
                    continue

                prompt_text = span.get("prompt_text")
                if prompt_text is None:
                    prompt_text = (span.get("text") or "").replace("\n", " ").strip()
                if len(prompt_text) > self._MAX_SPAN_TEXT_CHARS:
                    prompt_text = prompt_text[: self._MAX_SPAN_TEXT_CHARS - 3] + "..."

                bbox_raw = span.get("bbox")
                bbox_summary: Optional[List[float]] = None
                if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) >= 4:
                    coords: List[float] = []
                    for coord in bbox_raw[:4]:
                        try:
                            coords.append(round(float(coord), 2))
                        except (TypeError, ValueError):
                            coords.append(0.0)
                    bbox_summary = coords

                span_entry: Dict[str, Any] = {"id": span_id, "text": prompt_text}
                if bbox_summary is not None:
                    span_entry["bbox"] = bbox_summary

                spans_summary.append(span_entry)
                total_spans += 1

            truncated = 0
            if len(spans_summary) > self._MAX_SPANS_PER_PAGE:
                truncated = len(spans_summary) - self._MAX_SPANS_PER_PAGE
                spans_summary = spans_summary[: self._MAX_SPANS_PER_PAGE]
                spans_summary.append(
                    {
                        "id": "__truncated__",
                        "text": f"... omitted {truncated} spans beyond limit",
                    }
                )

            page_record = {
                "page": page_entry.get("page"),
                "span_count": len(spans_summary),
                "spans": spans_summary,
            }
            if truncated:
                page_record["truncated_spans"] = truncated

            inventory.append(page_record)

            if total_spans >= self._MAX_TOTAL_SPANS:
                remaining = sum(
                    len(pe.get("spans", []))
                    for pe in span_index[page_idx + 1 :]
                    if isinstance(pe, dict)
                )
                inventory.append(
                    {
                        "page": "__truncated__",
                        "span_count": 0,
                        "spans": [
                            {
                                "id": "__remaining__",
                                "text": f"Omitted {remaining} additional spans beyond global limit",
                            }
                        ],
                        "truncated_spans": remaining,
                    }
                )
                break

        return inventory

    def _extract_finish_reason(self, call_result: Dict[str, Any]) -> Optional[str]:
        raw_response = call_result.get("raw_response")
        if isinstance(raw_response, dict):
            raw_payload = raw_response.get("raw") or raw_response
            choices = raw_payload.get("choices") if isinstance(raw_payload, dict) else None
            if isinstance(choices, list):
                for choice in choices:
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        return str(finish_reason)
        return None

    def _normalize_vision_questions(
        self, questions: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not questions:
            return normalized

        for entry in questions:
            if not isinstance(entry, dict):
                continue
            stem_text = entry.get("stem_text") or entry.get("stem")
            q_number = (
                entry.get("question_number")
                or entry.get("q_number")
                or entry.get("id")
            )
            if not stem_text or not q_number:
                continue
            cloned = copy.deepcopy(entry)
            cloned["question_number"] = str(q_number).strip()
            normalized.append(cloned)
        return normalized

    def _index_span_records(self, pymupdf_data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        entries = (
            pymupdf_data.get("pymupdf_span_index")
            or pymupdf_data.get("span_index")
            or []
        )
        indexed: Dict[int, Dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            page = entry.get("page")
            if isinstance(page, int):
                indexed[page] = entry
        return indexed

    def _group_questions_by_page(
        self, questions: List[Dict[str, Any]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for question in questions:
            positioning = question.get("positioning") or {}
            page = positioning.get("page")
            try:
                page_int = int(page)
            except (TypeError, ValueError):
                continue
            grouped.setdefault(page_int, []).append(question)
        return grouped

    def _extract_tokens(self, text: str) -> set[str]:
        cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
        tokens = {token for token in cleaned.split() if len(token) >= 4}
        return tokens

    def _collect_question_spans(
        self,
        span_entry: Dict[str, Any],
        question: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        spans = span_entry.get("spans")
        if not isinstance(spans, list):
            return [], ["no span data in entry"]

        stem_text = question.get("stem_text") or ""
        stem_tokens = self._extract_tokens(stem_text)
        positioning = question.get("positioning") or {}
        bbox = positioning.get("bbox")
        expanded_bbox = self._expand_bbox(bbox) if self._is_bbox_valid(bbox) else None

        half_snippet = max(1, self._MAX_SPAN_TEXT_CHARS // 2)

        summaries: List[Dict[str, Any]] = []
        all_summaries: List[Dict[str, Any]] = []

        for span in spans:
            if not isinstance(span, dict):
                continue
            span_id = span.get("id")
            if not span_id:
                continue

            raw_text = (span.get("text") or "").replace("\n", " ")
            normalized = raw_text.strip()
            if not normalized:
                continue

            start_snippet = normalized[:half_snippet]
            end_snippet = (
                normalized[-half_snippet:]
                if len(normalized) > half_snippet
                else normalized
            )

            bbox_values = None
            try:
                bbox_candidate = span.get("bbox") or []
                if isinstance(bbox_candidate, (list, tuple)) and len(bbox_candidate) >= 4:
                    bbox_values = [float(bbox_candidate[i]) for i in range(4)]
            except (TypeError, ValueError):
                bbox_values = None

            if bbox_values:
                x0, y0, x1, y1 = bbox_values
                cx = (x0 + x1) / 2
                cy = (y0 + y1) / 2
                width = x1 - x0
                height = y1 - y0
            else:
                cx = cy = width = height = 0.0

            summary = {
                "id": span_id,
                "start": start_snippet,
                "end": end_snippet,
                "length": len(normalized),
                "center": [cx, cy],
                "size": [width, height],
                "_tokens": self._extract_tokens(normalized),
                "_text": normalized.lower(),
            }
            if bbox_values is not None:
                summary["bbox"] = bbox_values

            all_summaries.append(summary)

        warnings: List[str] = []

        if expanded_bbox:
            summaries = [
                summary
                for summary in all_summaries
                if summary.get("bbox")
                and self._bbox_intersects(summary["bbox"], expanded_bbox)
            ]
        else:
            summaries = []

        if not summaries and stem_tokens:
            def _token_score(summary: Dict[str, Any]) -> Tuple[int, int]:
                overlap = summary["_tokens"] & stem_tokens
                weight = sum(len(tok) for tok in overlap)
                return weight, len(overlap)

            scored = [
                (summary, *_token_score(summary))
                for summary in all_summaries
            ]
            scored = [item for item in scored if item[1] > 0]
            scored.sort(key=lambda item: (-item[1], -item[2]))
            summaries = [item[0] for item in scored[:6]]
            if summaries:
                warnings.append("token_overlap_fallback")

        if not summaries:
            # Final fallback: take the first few spans on the page
            summaries = all_summaries[:6]
            if summaries:
                warnings.append("span_window_fallback")

        summaries.sort(
            key=lambda s: (
                s["center"][1] if s.get("center") else 0.0,
                s["center"][0] if s.get("center") else 0.0,
            )
        )

        for summary in summaries:
            summary.pop("_tokens", None)
            summary.pop("_text", None)

        return summaries, warnings

    def _is_bbox_valid(self, bbox: Optional[List[float]]) -> bool:
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            try:
                float(bbox[0])
                return True
            except (TypeError, ValueError):
                return False
        return False

    def _expand_bbox(self, bbox: Optional[List[float]], margin: float = 12.0) -> Optional[List[float]]:
        if not self._is_bbox_valid(bbox):
            return None
        x0, y0, x1, y1 = [float(bbox[i]) for i in range(4)]
        return [x0 - margin, y0 - margin, x1 + margin, y1 + margin]

    def _bbox_intersects(self, a: List[float], b: List[float]) -> bool:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        if ax1 < bx0 or bx1 < ax0:
            return False
        if ay1 < by0 or by1 < ay0:
            return False
        return True

    def _merge_geometry_with_vision(
        self,
        vision_questions: List[Dict[str, Any]],
        geometry_by_question: Dict[str, Dict[str, Any]],
        warnings: List[str],
    ) -> List[Dict[str, Any]]:
        fused: List[Dict[str, Any]] = []
        for question in vision_questions:
            q_number = str(
                question.get("question_number")
                or question.get("q_number")
                or question.get("id")
                or ""
            ).strip()
            fused_entry = copy.deepcopy(question)
            geometry = geometry_by_question.get(q_number)
            positioning = fused_entry.setdefault("positioning", {})
            if "page" not in positioning and question.get("positioning", {}).get("page") is not None:
                positioning["page"] = question.get("positioning", {}).get("page")
            fused_entry.setdefault(
                "sources_detected",
                question.get("sources_detected") or ["openai_vision"],
            )
            if geometry:
                spans = geometry.get("stem_spans") or []
                bbox = geometry.get("stem_bbox")
                fused_entry["stem_spans"] = spans
                if bbox:
                    fused_entry["stem_bbox"] = bbox
                    positioning["bbox"] = bbox
                if spans:
                    positioning["stem_spans"] = spans
                    positioning["span_ids"] = spans
                    positioning.setdefault("source", "pymupdf")
            else:
                warnings.append(f"question {q_number}: geometry missing")
                metadata = fused_entry.setdefault("metadata", {})
                missing = metadata.setdefault("geometry_warnings", [])
                missing.append("span_enrichment_missing")

            fused.append(fused_entry)
        return fused

    def close(self) -> None:
        try:
            self.ai_client.close()
        except Exception:
            pass

    def _calculate_fusion_confidence(
        self,
        fused_questions: List[Dict[str, Any]],
        openai_result: AIExtractionResult,
        mistral_result: AIExtractionResult
    ) -> float:
        """Calculate confidence based on source agreement and quality."""
        if not fused_questions:
            return 0.0

        # Base confidence from source quality
        source_confidence = (openai_result.confidence + mistral_result.confidence) / 2

        # Bonus for source agreement
        agreement_bonus = 0.0
        total_sources = len(openai_result.questions) + len(mistral_result.questions)
        if total_sources > 0:
            agreement_ratio = len(fused_questions) / max(total_sources, 1)
            agreement_bonus = min(0.2, agreement_ratio * 0.1)

        # Quality bonus for complete questions
        quality_bonus = 0.0
        complete_questions = sum(
            1 for q in fused_questions
            if q.get('stem_text') and (q.get('options') or q.get('question_type') in ['short_answer', 'fill_blank'])
        )
        if fused_questions:
            quality_ratio = complete_questions / len(fused_questions)
            quality_bonus = quality_ratio * 0.1

        final_confidence = min(0.95, source_confidence + agreement_bonus + quality_bonus)
        return round(final_confidence, 2)

    def _create_question_analysis_prompt(self, text_elements: List[Dict]) -> str:
        """Create prompt for GPT-5 to analyze elements and generate question mappings."""

        # Create element summary for analysis (limit to prevent token overflow)
        element_summary = []
        for i, elem in enumerate(text_elements[:50]):
            content = elem.get("content", "").strip()
            if len(content) > 100:
                content = content[:97] + "..."

            element_summary.append({
                "id": i,
                "content": content,
                "bbox": elem.get("bbox", [0, 0, 0, 0]),
                "font": elem.get("font", ""),
                "size": elem.get("size", 0)
            })

        return f"""
Analyze these PDF text elements (with precise positioning) to identify questions and generate strategic manipulation targets.

ELEMENTS:
{json.dumps(element_summary, indent=2)}

TASK: Generate question-level analysis with substring manipulation targets for precision overlay approach.

EXPECTED STRATEGIES:
1. **Question Numbers**: "1" → "A", "2" → "B" (number to letter confusion)
2. **Option Labels**: "a" → "b", "b" → "c", "c" → "d", "d" → "a" (rotation)
3. **Key Terms**: Strategic word replacements in stems
4. **Answer Confusion**: Subtle content changes that affect correctness

OUTPUT FORMAT (JSON only):
{{
  "questions": [
    {{
      "question_id": "q1",
      "question_number": "1",
      "question_type": "mcq_single",
      "stem_elements": [0, 1, 2],
      "option_elements": [3, 4, 5, 6],
      "manipulation_targets": [
        {{
          "target_type": "question_number",
          "element_id": 0,
          "original_substring": "Question - 1:",
          "replacement_substring": "Question - A:",
          "bbox": [72.0, 72.51, 90.0, 85.79],
          "font": "TimesNewRomanPS-BoldMT",
          "size": 12.0,
          "strategy": "number_to_letter",
          "impact": "high"
        }},
        {{
          "target_type": "option_label",
          "element_id": 3,
          "original_substring": "a.",
          "replacement_substring": "b.",
          "bbox": [90.0, 100.37, 95.0, 113.66],
          "font": "TimesNewRomanPSMT",
          "size": 12.0,
          "strategy": "option_rotation",
          "impact": "high"
        }}
      ],
      "confidence": 0.95
    }}
  ],
  "analysis": {{
    "domain": "academic",
    "question_count": 6,
    "manipulation_strategy": "strategic_confusion",
    "high_impact_targets": 12
  }}
}}

RULES:
1. Focus on HIGH-IMPACT manipulations (question numbers, option labels)
2. Use EXACT substrings from element content
3. Preserve visual layout (similar character counts)
4. Ensure precise bbox coordinates for overlay targeting
5. Create semantic confusion without obvious errors
6. Return ONLY valid JSON

Analyze and identify questions with strategic manipulation opportunities.
"""

    def _parse_question_analysis_response(self, content: str) -> List[Dict[str, Any]]:
        """Parse GPT-5 question analysis response."""
        try:
            # Clean up response
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                nl_pos = content.find("\n")
                if nl_pos != -1:
                    content = content[nl_pos + 1:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            # Extract JSON
            start = content.find('{')
            end = content.rfind('}')
            if start == -1 or end == -1:
                return []

            json_str = content[start:end + 1]
            parsed = json.loads(json_str)

            questions = parsed.get('questions', [])
            validated_questions = []

            for q in questions:
                if isinstance(q, dict) and q.get('question_id') and q.get('manipulation_targets'):
                    # Validate manipulation targets
                    validated_targets = []
                    for target in q.get('manipulation_targets', []):
                        if (isinstance(target, dict) and
                            target.get('original_substring') and
                            target.get('replacement_substring') and
                            target.get('bbox')):

                            # Ensure required fields
                            target.setdefault('target_type', 'unknown')
                            target.setdefault('strategy', 'substitution')
                            target.setdefault('impact', 'medium')
                            target.setdefault('font', '')
                            target.setdefault('size', 12.0)

                            validated_targets.append(target)

                    if validated_targets:
                        q['manipulation_targets'] = validated_targets
                        q.setdefault('question_type', 'mcq_single')
                        q.setdefault('confidence', 0.8)
                        q.setdefault('stem_elements', [])
                        q.setdefault('option_elements', [])
                        validated_questions.append(q)

            return validated_questions

        except json.JSONDecodeError as e:
            self.logger.warning(f"GPT-5 question analysis JSON parsing failed: {e}", content=content[:200])
            return []
        except Exception as e:
            self.logger.warning(f"GPT-5 question analysis parsing failed: {e}")
            return []

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate GPT-4 API cost in cents."""
        # GPT-4 pricing: ~$0.03 per 1K prompt tokens, ~$0.06 per 1K completion tokens
        prompt_cost = (prompt_tokens / 4 / 1000) * 3.0  # Rough token estimation
        completion_cost = (completion_tokens / 4 / 1000) * 6.0
        return prompt_cost + completion_cost
