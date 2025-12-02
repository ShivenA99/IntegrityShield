from __future__ import annotations

from abc import ABC
import difflib
from bisect import bisect_left, bisect_right
from collections import OrderedDict, defaultdict
import copy
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Tuple, Optional, TYPE_CHECKING

import fitz
from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    NameObject,
    NumberObject,
    TextStringObject,
)

from ...data_management.structured_data_manager import StructuredDataManager
from ....models.pipeline import PipelineRun, QuestionManipulation
from ....utils.logging import get_logger
from .span_extractor import collect_span_records

if TYPE_CHECKING:  # pragma: no cover
    from .span_rewrite_plan import SpanRewriteEntry


class BaseRenderer:
    _ZERO_WIDTH_MARKERS = (
        "\u200B",  # zero-width space
        "\u200C",  # zero-width non-joiner
        "\u200D",  # zero-width joiner
        "\u2060",  # word joiner
        "\u2061",  # function application
        "\u2062",  # invisible times
        "\u2063",  # invisible separator
        "\ufeff",  # byte-order mark
    )

    _NORMALIZATION_TABLE = str.maketrans(
        {
            "ﬁ": "fi",
            "ﬂ": "fl",
            "ﬀ": "ff",
            "ﬃ": "ffi",
            "ﬄ": "ffl",
            "ﬅ": "ft",
            "ﬆ": "st",
            "–": "-",
            "—": "-",
            "−": "-",
            "‑": "-",
            "‐": "-",
            "“": '"',
            "”": '"',
            "‟": '"',
            "’": "'",
            "‘": "'",
            "‚": ",",
            "‛": "'",
            "…": "...",
            " ": " ",  # non-breaking space
            "^": "",
            "ˆ": "",
        }
    )

    _SPACE_THRESHOLD = -80.0

    def __init__(self) -> None:
        self.structured_manager = StructuredDataManager()
        self.logger = get_logger(self.__class__.__name__)
        self._span_record_cache: Dict[int, Dict[str, object]] = {}
        self._span_cache_run_id: Optional[str] = None

    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        """Generate an enhanced PDF and return metadata. Base implementation returns empty metadata."""
        return {"file_size_bytes": 0, "effectiveness_score": 0.0}

    def discover_tokens_from_layout(self, run_id: str, pdf_bytes: bytes) -> Dict[str, int]:
        """Discover potential mapping tokens from PDF layout analysis."""
        import fitz
        import unicodedata
        import re

        discovered_tokens: Dict[str, int] = {}

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_num in range(len(doc)):
                page = doc[page_num]
                raw = page.get_text("rawdict") or {}
                blocks = raw.get("blocks") or []

                for block in blocks:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_text = span.get("text", "")
                            if not span_text:
                                continue

                            # Normalize text
                            normalized = unicodedata.normalize("NFKC", span_text)

                            # Extract meaningful tokens using regex
                            tokens = re.findall(r'\b\w{2,}\b', normalized)

                            for token in tokens:
                                # Filter out pure numbers and very common words
                                if (token.isdigit() or
                                    token.lower() in {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those', 'a', 'an'}):
                                    continue

                                # Count token frequencies
                                normalized_token = token.strip()
                                if len(normalized_token) >= 2:
                                    discovered_tokens[normalized_token] = discovered_tokens.get(normalized_token, 0) + 1
                                    # Also add casefold version
                                    casefold_token = normalized_token.casefold()
                                    if casefold_token != normalized_token:
                                        discovered_tokens[casefold_token] = discovered_tokens.get(casefold_token, 0) + 1

            doc.close()

        except Exception:
            pass

        return discovered_tokens

    def build_enhanced_mapping_with_discovery(self, run_id: str, pdf_bytes: bytes = None) -> Tuple[Dict[str, str], Dict[str, int]]:
        """Build mapping with discovered tokens for enhanced coverage."""
        # Get base mapping from questions (markers already embedded)
        base_mapping = self.build_mapping_from_questions(run_id)

        # Discover additional tokens if PDF bytes provided
        discovered_tokens: Dict[str, int] = {}
        if pdf_bytes:
            discovered_tokens = self.discover_tokens_from_layout(run_id, pdf_bytes)

        # Create enhanced mapping by adding discovered tokens as identity mappings
        # This allows the stream rewriter to find and process them even if not in original mapping
        enhanced_mapping = OrderedDict(base_mapping)

        # Add high-frequency discovered tokens as identity mappings (token → token)
        # This helps the decoder find more text to analyze during stream processing
        min_frequency = 2  # Only include tokens that appear multiple times
        for token, frequency in discovered_tokens.items():
            if frequency >= min_frequency:
                marker = self._encode_marker(f"{run_id}:discovery:{token}:{frequency}")
                key = f"{token}{marker}"
                if key not in enhanced_mapping:
                    enhanced_mapping[key] = f"{token}{marker}"

        # Log discovery results
        try:
            from ...developer.live_logging_service import live_logging_service

            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "INFO",
                "token discovery completed",
                component=self.__class__.__name__,
                context={
                    "base_mapping_size": len(base_mapping),
                    "discovered_tokens": len(discovered_tokens),
                    "enhanced_mapping_size": len(enhanced_mapping),
                    "top_discovered": sorted(discovered_tokens.items(), key=lambda x: x[1], reverse=True)[:10],
                },
            )
        except Exception:
            pass

        return enhanced_mapping, discovered_tokens

    def build_mapping_from_questions(self, run_id: str) -> Dict[str, str]:
        structured = self.structured_manager.load(run_id)
        mapping: Dict[str, str] = OrderedDict()

        source = "structured"

        def append_entries(entries: Iterable[dict], q_label: str, entry_prefix: str = "structured") -> None:
            for entry_idx, entry in enumerate(entries):
                original_raw = (entry or {}).get("original") or ""
                replacement_raw = (entry or {}).get("replacement") or ""
                original = original_raw.strip()
                replacement = replacement_raw.strip()
                if not original or not replacement:
                    continue
                spans = self._split_multi_span(original, replacement) or [(original, replacement)]
                for span_idx, (span_orig, span_repl) in enumerate(spans):
                    key_span = span_orig.strip()
                    val_span = span_repl.strip()
                    if not key_span or not val_span:
                        continue
                    marker = self._encode_marker(
                        f"{run_id}:{entry_prefix}:{q_label}:{entry_idx}:{span_idx}"
                    )
                    key = f"{key_span}{marker}"
                    value = f"{val_span}{marker}"
                    mapping[key] = value

        if structured:
            questions = structured.get("questions", []) or []
            for idx, question in enumerate(questions):
                manipulation = question.get("manipulation", {}) or {}
                substring_mappings = manipulation.get("substring_mappings", []) or []
                if not substring_mappings:
                    continue
                q_label = str(question.get("q_number") or question.get("question_number") or (idx + 1))
                append_entries(substring_mappings, q_label)

        if not mapping:
            rows = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
            for idx, question in enumerate(rows):
                entries = list(question.substring_mappings or [])
                if not entries:
                    continue
                q_label = str(getattr(question, "question_number", None) or question.id or (idx + 1))
                append_entries(entries, q_label, entry_prefix="database")
            source = "database"

        try:
            from ...developer.live_logging_service import live_logging_service

            sample = [
                {
                    "orig": self.strip_zero_width(k),
                    "repl": self.strip_zero_width(v),
                }
                for k, v in list(mapping.items())[:5]
            ]
            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "INFO",
                f"Renderer mapping prepared from {source}",
                component=self.__class__.__name__,
                context={
                    "mapping_source": source,
                    "entries": len(mapping),
                    "sample": sample,
                },
            )
        except Exception:
            pass

        return mapping

    def build_mapping_context(self, run_id: str | None) -> Dict[str, List[Dict[str, object]]]:
        """Return deterministic substring context keyed by cleaned original text."""
        contexts: "defaultdict[str, List[Dict[str, object]]]" = defaultdict(list)
        if not run_id:
            return contexts

        if run_id and run_id != self._span_cache_run_id:
            self._span_record_cache = {}
            self._span_cache_run_id = run_id

        structured = self.structured_manager.load(run_id)
        questions = (structured.get("questions") if structured else []) or []
        question_index = (structured.get("question_index") if structured else []) or []
        index_by_q = {
            str(entry.get("q_number")): entry
            for entry in question_index
            if entry.get("q_number") is not None
        }

        db_models: Dict[str, QuestionManipulation] = {}
        try:
            for model in QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all():
                db_models[str(model.question_number)] = model
        except Exception as exc:  # pragma: no cover - DB not available in some offline tests
            self.logger.warning(
                "Unable to load question_manipulations for run %s: %s", run_id, exc
            )

        seen_qnums: set[str] = set()
        missing_payloads: set[str] = set()

        def process_question(
            q_label: str,
            structured_entry: Optional[dict],
            model: Optional[QuestionManipulation],
        ) -> None:
            if not q_label:
                return
            try:
                payload = self._assemble_question_payload(
                    q_label,
                    structured_entry or {},
                    index_by_q.get(q_label, {}),
                    model,
                    run_id,
                )
            except ValueError as exc:
                self.logger.error("%s", exc)
                missing_payloads.add(q_label)
                return

            contexts_for_question = self._build_contexts_from_payload(payload)
            for ctx in contexts_for_question:
                contexts[ctx["original"]].append(ctx)
            seen_qnums.add(q_label)

        for entry in questions:
            label = str(entry.get("q_number") or entry.get("question_number") or "").strip()
            process_question(label, entry, db_models.get(label))

        for label, model in db_models.items():
            if label in seen_qnums:
                continue
            process_question(label, None, model)

        if missing_payloads:
            message = (
                f"Unable to assemble deterministic question context for run {run_id}: "
                f"missing payload for {sorted(missing_payloads)}"
            )
            raise ValueError(message)

        for entries in contexts.values():
            entries.sort(
                key=lambda ctx: (
                    ctx.get("page", -1) if isinstance(ctx.get("page"), int) else -1,
                    ctx.get("start_pos", -1) if isinstance(ctx.get("start_pos"), int) else -1,
                    ctx.get("entry_index", 0),
                )
            )

        total_contexts = sum(len(v) for v in contexts.values())
        if total_contexts:
            self.logger.debug(
                "Prepared %d substring contexts across %d originals for run %s",
                total_contexts,
                len(contexts),
                run_id,
            )

        return contexts

    def strip_zero_width(self, text: str | None) -> str:
        if not text:
            return ""
        return "".join(ch for ch in text if ch not in self._ZERO_WIDTH_MARKERS)

    def _normalize_for_span_match(self, value: str | None) -> str:
        if not value:
            return ""
        cleaned = self.strip_zero_width(value)
        cleaned = cleaned.translate(self._NORMALIZATION_TABLE)
        collapsed = " ".join(cleaned.split())
        return collapsed.strip()

    def _normalize_for_compare(self, value: str | None) -> str:
        return self._normalize_for_span_match(value).lower()

    def _build_normalized_map(self, value: str | None) -> Tuple[str, List[int]]:
        """Return normalized text alongside glyph index mapping for span comparisons."""
        if not value:
            return "", []

        stripped = self.strip_zero_width(value)
        normalized_chars: List[str] = []
        index_map: List[int] = []
        last_was_space = False

        for glyph_index, raw_char in enumerate(stripped):
            translated = raw_char.translate(self._NORMALIZATION_TABLE)
            if not translated:
                translated = raw_char

            for piece in translated:
                char = " " if piece.isspace() else piece
                if char == " ":
                    if last_was_space:
                        continue
                    last_was_space = True
                else:
                    last_was_space = False

                normalized_chars.append(char)
                index_map.append(glyph_index)

        if not normalized_chars:
            return "", []

        start_trim = 0
        end_trim = len(normalized_chars)
        while start_trim < end_trim and normalized_chars[start_trim] == " ":
            start_trim += 1
        while end_trim > start_trim and normalized_chars[end_trim - 1] == " ":
            end_trim -= 1

        if start_trim or end_trim != len(normalized_chars):
            normalized_chars = normalized_chars[start_trim:end_trim]
            index_map = index_map[start_trim:end_trim]

        return "".join(normalized_chars), index_map

    def _assemble_question_payload(
        self,
        q_label: str,
        structured_entry: Dict[str, object],
        index_entry: Dict[str, object],
        model: Optional[QuestionManipulation],
        run_id: Optional[str],
    ) -> Dict[str, object]:
        stem_text = (
            structured_entry.get("stem_text")
            or structured_entry.get("original_text")
            or (model.original_text if model else "")
            or ""
        )

        question_type = structured_entry.get("question_type") or (
            model.question_type if model else None
        )

        options = copy.deepcopy(structured_entry.get("options")) if structured_entry.get("options") else None
        if options is None and model and model.options_data:
            options = copy.deepcopy(model.options_data)

        manip_structured = copy.deepcopy(
            ((structured_entry.get("manipulation") or {}).get("substring_mappings") or [])
        )
        manip_db = copy.deepcopy(list(model.substring_mappings or [])) if model else []
        substring_mappings = manip_structured or manip_db

        # Gather positioning clues
        page = None
        bbox = None

        def consume_positioning(source: Optional[Dict[str, object]]) -> None:
            nonlocal page, bbox
            if not isinstance(source, dict):
                return
            if page is None:
                candidate_page = source.get("page") or source.get("page_number")
                if candidate_page is not None:
                    page = candidate_page
            candidate_bbox = source.get("bbox") if isinstance(source.get("bbox"), (list, tuple)) else None
            if bbox is None and candidate_bbox and len(candidate_bbox) == 4:
                bbox = tuple(float(v) for v in candidate_bbox)

        consume_positioning(structured_entry.get("positioning"))
        consume_positioning(structured_entry.get("stem_position"))
        if isinstance(index_entry, dict):
            if page is None:
                page = index_entry.get("page")
            stem_info = index_entry.get("stem") if isinstance(index_entry.get("stem"), dict) else {}
            consume_positioning(stem_info)

        if model and model.stem_position:
            consume_positioning(model.stem_position)

        page_idx = self._safe_page_index(page)

        if substring_mappings:
            if (page_idx is None or bbox is None) and run_id:
                rec_page, rec_bbox = self._recover_question_geometry(
                    run_id,
                    stem_text,
                )
                if page_idx is None:
                    page_idx = rec_page
                if bbox is None:
                    bbox = rec_bbox

            if page_idx is None:
                raise ValueError(
                    f"Question {q_label} missing page index for deterministic matching"
                )

            if not bbox:
                raise ValueError(
                    f"Question {q_label} missing stem bounding box for deterministic matching"
                )

        stem_span_ids: List[str] = []

        def collect_span_ids(source: Optional[Dict[str, object]]) -> None:
            nonlocal stem_span_ids
            if not isinstance(source, dict):
                return
            if stem_span_ids:
                return
            candidates = source.get("stem_spans") or source.get("span_ids") or source.get("spans")
            if isinstance(candidates, list):
                stem_span_ids = [str(entry) for entry in candidates if entry]
            elif isinstance(candidates, str):
                stem_span_ids = [candidates]

        collect_span_ids(structured_entry)
        collect_span_ids(structured_entry.get("stem"))  # type: ignore[arg-type]
        collect_span_ids(structured_entry.get("positioning"))  # type: ignore[arg-type]
        collect_span_ids(index_entry)
        collect_span_ids(index_entry.get("stem"))  # type: ignore[arg-type]
        if model and model.stem_position:
            collect_span_ids(model.stem_position)
            stem_bbox = model.stem_position.get("bbox")
            try:
                if stem_bbox and len(stem_bbox) == 4:
                    bbox = tuple(float(v) for v in stem_bbox)
            except (TypeError, ValueError):
                pass

        payload: Dict[str, object] = {
            "q_number": q_label,
            "stem_text": stem_text,
            "page": page_idx,
            "stem_bbox": bbox,
            "question_type": question_type,
            "options": options,
            "substring_mappings": substring_mappings,
        }

        if stem_span_ids:
            payload["stem_spans"] = stem_span_ids

        return payload

    def _normalize_bbox(self, value: object) -> Optional[Tuple[float, float, float, float]]:
        if isinstance(value, (list, tuple)) and len(value) == 4:
            try:
                return tuple(float(v) for v in value)
            except (TypeError, ValueError):
                return None
        return None

    def _normalize_quads(self, value: object) -> List[List[float]]:
        quads: List[List[float]] = []
        if isinstance(value, (list, tuple)):
            for quad in value:
                if isinstance(quad, (list, tuple)) and len(quad) == 8:
                    try:
                        quads.append([float(v) for v in quad])
                    except (TypeError, ValueError):
                        continue
        return quads

    def _rect_from_quads(self, quads: List[List[float]]) -> Optional[fitz.Rect]:
        if not quads:
            return None
        try:
            union = fitz.Quad(quads[0]).rect
            for quad in quads[1:]:
                q = fitz.Quad(quad)
                union |= q.rect
            return union
        except Exception:
            return None

    def _span_info_from_rect(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        context: Dict[str, object],
    ) -> Optional[Tuple[fitz.Rect, float, int]]:
        original = self.strip_zero_width(str(context.get("original") or "")).strip()
        if not original:
            return None

        raw = page.get_text("rawdict") or {}
        needle_cf = original.casefold()

        for block_index, block in enumerate(raw.get("blocks", [])):
            for line_index, line in enumerate(block.get("lines", [])):
                for span_index, span in enumerate(line.get("spans", [])):
                    span_bbox = span.get("bbox")
                    if not span_bbox:
                        continue
                    try:
                        span_rect = fitz.Rect(*span_bbox)
                    except Exception:
                        continue
                    if not span_rect.intersects(rect):
                        continue

                    chars = span.get("chars", [])
                    if not chars:
                        continue
                    text = "".join(ch.get("c", "") for ch in chars)
                    lowered = text.casefold()
                    start = lowered.find(needle_cf)
                    while start != -1:
                        end = start + len(needle_cf)
                        if end > len(chars):
                            break
                        try:
                            char_rect = fitz.Rect(chars[start]["bbox"])
                            for ch in chars[start + 1 : end]:
                                char_rect |= fitz.Rect(ch["bbox"])
                        except Exception:
                            char_rect = fitz.Rect(span_bbox)

                        if not char_rect.intersects(rect):
                            start = lowered.find(needle_cf, start + 1)
                            continue

                        fontsize = float(span.get("size", 10.0))
                        fontname = span.get("font")
                        first_origin = None
                        last_origin = None
                        if chars:
                            try:
                                first_origin = tuple(chars[start].get("origin", (char_rect.x0, char_rect.y0)))
                            except Exception:
                                first_origin = None
                            try:
                                last_origin = tuple(chars[end - 1].get("origin", (char_rect.x1, char_rect.y1)))
                            except Exception:
                                last_origin = None
                        context["matched_font"] = fontname
                        context["matched_fontsize"] = fontsize
                        if first_origin:
                            context["matched_origin_x"] = float(first_origin[0])
                            context["matched_origin_y"] = float(first_origin[1])
                        if last_origin:
                            context["matched_end_origin_x"] = float(last_origin[0])
                            context["matched_end_origin_y"] = float(last_origin[1])
                        context["matched_rect_width"] = float(char_rect.width)
                        context["matched_text"] = text[start:end]
                        context["matched_rect"] = tuple(char_rect)
                        context["matched_fontsize"] = fontsize
                        context["matched_span_len"] = end - start
                        context["matched_glyph_path"] = {
                            "block": block_index,
                            "line": line_index,
                            "span": span_index,
                            "char_start": start,
                            "char_end": end,
                        }
                        return char_rect, fontsize, end - start

        return None

    def _build_contexts_from_payload(self, payload: Dict[str, object]) -> List[Dict[str, object]]:
        contexts: List[Dict[str, object]] = []
        stem_text_raw = payload.get("stem_text") or ""
        stem_text = self.strip_zero_width(str(stem_text_raw))
        page = payload.get("page")
        bbox = payload.get("stem_bbox")
        stem_span_ids = [
            str(span_id)
            for span_id in (payload.get("stem_spans") or [])
            if span_id
        ]
        q_label = str(payload.get("q_number") or "")

        substring_mappings = payload.get("substring_mappings") or []
        if not isinstance(substring_mappings, list):
            return contexts

        for entry_index, mapping in enumerate(substring_mappings):
            if not isinstance(mapping, dict):
                continue

            original_raw = mapping.get("original") or ""
            replacement_raw = mapping.get("replacement") or ""
            original = self.strip_zero_width(str(original_raw)).strip()
            replacement = self.strip_zero_width(str(replacement_raw)).strip()

            if not original or not replacement:
                continue

            start_pos = mapping.get("start_pos")
            end_pos = mapping.get("end_pos")
            try:
                start_pos_int = int(start_pos)
                end_pos_int = int(end_pos)
            except (TypeError, ValueError):
                raise ValueError(
                    f"Question {q_label} mapping '{original}' missing valid span positions"
                )

            if end_pos_int <= start_pos_int:
                raise ValueError(
                    f"Question {q_label} mapping '{original}' has invalid span bounds"
                )

            span_start, span_end = self._normalize_span_position(
                stem_text,
                original,
                start_pos_int,
                end_pos_int,
            )

            occurrence_index = self._compute_occurrence_index(stem_text, original, span_start)

            prefix_window = 24
            suffix_window = 24
            prefix = stem_text[max(0, span_start - prefix_window) : span_start]
            suffix = stem_text[span_end : span_end + suffix_window]

            fingerprint = {
                "prefix": prefix,
                "original": original,
                "suffix": suffix,
                "occurrence": occurrence_index,
            }

            selection_bbox = self._normalize_bbox(mapping.get("selection_bbox"))
            selection_quads = self._normalize_quads(mapping.get("selection_quads"))
            selection_page = mapping.get("selection_page")
            try:
                selection_page_idx = int(selection_page)
            except (TypeError, ValueError):
                selection_page_idx = None

            if selection_page_idx is not None:
                page = selection_page_idx
                page_idx = self._safe_page_index(selection_page_idx)

            union_rect = None
            if selection_quads:
                union_rect = self._rect_from_quads(selection_quads)
            if not selection_bbox and union_rect is not None:
                selection_bbox = tuple(union_rect)

            context = {
                "original": original,
                "replacement": replacement,
                "page": page,
                "stem_bbox": tuple(bbox) if bbox else None,
                "q_number": q_label,
                "entry_index": entry_index,
                "start_pos": span_start,
                "end_pos": span_end,
                "prefix": prefix,
                "suffix": suffix,
                "fingerprint": fingerprint,
                "fingerprint_key": self._fingerprint_key(fingerprint),
                "occurrence_index": occurrence_index,
                "stem_text": stem_text,
                "question_type": payload.get("question_type"),
                "options": payload.get("options"),
                "selection_page": selection_page_idx,
                "selection_bbox": tuple(selection_bbox) if selection_bbox else None,
                "selection_quads": selection_quads,
            }

            mapping_span_ids_raw = (
                mapping.get("selection_span_ids")
                or mapping.get("span_ids")
                or mapping.get("spans")
            )
            if isinstance(mapping_span_ids_raw, (list, tuple)):
                span_id_list = [str(span_id) for span_id in mapping_span_ids_raw if span_id]
            elif isinstance(mapping_span_ids_raw, str):
                span_id_list = [mapping_span_ids_raw]
            else:
                span_id_list = []

            if span_id_list:
                context["span_ids"] = span_id_list
                context["selection_span_ids"] = span_id_list

            if stem_span_ids:
                context["stem_span_ids"] = list(stem_span_ids)
                context.setdefault("span_ids", list(stem_span_ids))

            if selection_bbox:
                context["bbox"] = tuple(selection_bbox)
            elif bbox:
                context["bbox"] = tuple(bbox)

            contexts.append(context)

        return contexts

    def _fingerprint_matches(
        self,
        occurrence: Dict[str, object],
        expected_prefix: str,
        expected_suffix: str,
    ) -> bool:
        actual_prefix = self._normalize_for_compare(str(occurrence.get("prefix") or ""))
        actual_suffix = self._normalize_for_compare(str(occurrence.get("suffix") or ""))
        expected_prefix_clean = self._normalize_for_compare(expected_prefix)
        expected_suffix_clean = self._normalize_for_compare(expected_suffix)

        prefix_ok = True
        if expected_prefix_clean:
            compare = actual_prefix[-min(len(actual_prefix), len(expected_prefix_clean)) :]
            expected_tail = expected_prefix_clean[-min(len(actual_prefix), len(expected_prefix_clean)) :]
            prefix_ok = compare == expected_tail

        suffix_ok = True
        if expected_suffix_clean:
            compare = actual_suffix[: min(len(actual_suffix), len(expected_suffix_clean))]
            expected_head = expected_suffix_clean[: min(len(actual_suffix), len(expected_suffix_clean))]
            suffix_ok = compare == expected_head

        return prefix_ok and suffix_ok

    def _fingerprint_key(self, fingerprint: Dict[str, object]) -> str:
        parts = [
            str(fingerprint.get("prefix") or ""),
            str(fingerprint.get("original") or ""),
            str(fingerprint.get("suffix") or ""),
            str(fingerprint.get("occurrence") or 0),
        ]
        raw = "|".join(parts)
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _collect_span_text(
        self,
        span_map: Dict[str, Dict[str, object]],
        span_ids: Iterable[str],
    ) -> str:
        parts: List[str] = []
        for span_id in span_ids:
            record = span_map.get(span_id)
            if not record:
                continue
            text = record.get("text") or ""
            normalized = self._normalize_for_span_match(text)
            if normalized:
                parts.append(normalized)
        return " ".join(parts)

    def _compact_text(self, value: str) -> str:
        return re.sub(r"[^0-9a-z]+", "", value)

    def _substring_in_text(self, substring: str, text: str) -> bool:
        if not substring or not text:
            return False
        normalized_sub = self._normalize_for_compare(substring)
        normalized_text = self._normalize_for_compare(text)
        if normalized_sub in normalized_text:
            return True
        compact_sub = self._compact_text(normalized_sub)
        compact_text = self._compact_text(normalized_text)
        return compact_sub in compact_text

    def _build_span_index(
        self,
        span_records: List[Dict[str, object]],
    ) -> Tuple[str, List[Tuple[str, int, int]]]:
        composite_parts: List[str] = []
        span_ranges: List[Tuple[str, int, int]] = []
        cursor = 0

        for record in span_records:
            span_id = str(record.get("id"))
            raw_text = record.get("text") or ""
            normalized = self._normalize_for_span_match(raw_text)
            if not normalized:
                continue
            if composite_parts and not composite_parts[-1].endswith(" "):
                composite_parts.append(" ")
                cursor += 1
            start = cursor
            composite_parts.append(normalized)
            cursor += len(normalized)
            end = cursor
            span_ranges.append((span_id, start, end))

        composite = "".join(composite_parts)
        return composite, span_ranges

    def _find_occurrence_positions(self, text: str, substring: str) -> List[Tuple[int, int]]:
        positions: List[Tuple[int, int]] = []
        lower_text = text.lower()
        lower_sub = substring.lower()
        start = 0
        sub_len = len(lower_sub)
        occurrence = 0
        while True:
            idx = lower_text.find(lower_sub, start)
            if idx == -1:
                break
            positions.append((occurrence, idx))
            occurrence += 1
            start = idx + sub_len
        return positions

    def _union_rect_for_span_ids(
        self,
        span_map: Dict[str, Dict[str, object]],
        span_ids: Iterable[str],
    ) -> Optional[fitz.Rect]:
        rect: Optional[fitz.Rect] = None
        for span_id in span_ids:
            record = span_map.get(span_id)
            if not record:
                continue
            bbox = record.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                span_rect = fitz.Rect(*bbox)
            except Exception:
                continue
            rect = span_rect if rect is None else rect | span_rect
        return rect

    def _match_single_span_by_similarity(
        self,
        span_records: List[Dict[str, object]],
        span_map: Dict[str, Dict[str, object]],
        substring: str,
    ) -> Optional[Tuple[List[str], Optional[fitz.Rect]]]:
        target = self._normalize_for_compare(substring)
        if not target:
            return None
        target_compact = self._compact_text(target)
        best_candidate: Optional[Tuple[List[str], Optional[fitz.Rect]]] = None
        best_score = 0.0

        for record in span_records:
            span_id = str(record.get("id"))
            raw_text = record.get("text") or ""
            normalized = self._normalize_for_compare(raw_text)
            if not normalized:
                continue
            normalized_compact = self._compact_text(normalized)
            if target_compact and target_compact in normalized_compact:
                rect = self._union_rect_for_span_ids(span_map, [span_id])
                return [span_id], rect
            score = difflib.SequenceMatcher(None, normalized_compact, target_compact).ratio()
            if score > best_score:
                best_score = score
                rect = self._union_rect_for_span_ids(span_map, [span_id])
                best_candidate = ([span_id], rect)

        if best_candidate and best_score >= 0.6:
            return best_candidate
        return None

    def _fallback_span_ids_by_text(
        self,
        span_records: List[Dict[str, object]],
        span_map: Dict[str, Dict[str, object]],
        substring: str,
        expected_prefix: Optional[str],
        expected_suffix: Optional[str],
        occurrence_hint: Optional[int],
    ) -> Optional[Tuple[List[str], Optional[fitz.Rect]]]:
        composite, span_ranges = self._build_span_index(span_records)
        target = self._normalize_for_compare(substring)
        if not target:
            return None

        occurrence_positions = self._find_occurrence_positions(composite, target)
        if not occurrence_positions:
            loose_match = self._match_single_span_by_similarity(span_records, span_map, substring)
            if loose_match:
                return loose_match
            return None

        expected_prefix_norm = self._normalize_for_compare(expected_prefix)
        expected_suffix_norm = self._normalize_for_compare(expected_suffix)
        target_len = len(target)

        chosen_start: Optional[int] = None
        chosen_order: Optional[int] = None

        if occurrence_hint is not None:
            for order, idx in occurrence_positions:
                if order == occurrence_hint:
                    chosen_order = order
                    chosen_start = idx
                    break

        if chosen_start is None:
            best_score = float("-inf")
            for order, idx in occurrence_positions:
                score = 0
                if expected_prefix_norm:
                    prefix_segment = composite[max(0, idx - len(expected_prefix_norm)) : idx]
                    if prefix_segment.endswith(expected_prefix_norm):
                        score += 2
                if expected_suffix_norm:
                    suffix_segment = composite[
                        idx + target_len : idx + target_len + len(expected_suffix_norm)
                    ]
                    if suffix_segment.startswith(expected_suffix_norm):
                        score += 2
                if occurrence_hint is not None:
                    score -= abs(order - occurrence_hint)
                if score > best_score:
                    best_score = score
                    chosen_order = order
                    chosen_start = idx

        if chosen_start is None:
            chosen_order, chosen_start = occurrence_positions[0]

        substring_start = chosen_start
        substring_end = substring_start + target_len

        selected_ids: List[str] = []
        union_rect: Optional[fitz.Rect] = None

        for span_id, span_start, span_end in span_ranges:
            if span_end <= substring_start or span_start >= substring_end:
                continue
            selected_ids.append(span_id)
            record = span_map.get(span_id)
            if not record:
                continue
            bbox = record.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            try:
                span_rect = fitz.Rect(*bbox)
            except Exception:
                continue
            union_rect = span_rect if union_rect is None else union_rect | span_rect

        if not selected_ids:
            return None

        return list(dict.fromkeys(selected_ids)), union_rect

    def _safe_page_index(self, page_value: object) -> Optional[int]:
        if page_value is None:
            return None
        try:
            page_int = int(page_value)
        except (TypeError, ValueError):
            return None
        if page_int < 0:
            return None
        if page_int == 0:
            return 0
        return page_int - 1

    def _normalize_span_position(
        self,
        stem_text: str,
        original: str,
        start_pos: int,
        end_pos: int,
    ) -> Tuple[int, int]:
        if start_pos < 0:
            start_pos = 0
        if end_pos < start_pos:
            end_pos = start_pos + len(original)

        expected_len = end_pos - start_pos
        actual_slice = stem_text[start_pos:end_pos]

        if actual_slice == original and expected_len == len(original):
            return start_pos, end_pos

        # Search locally for the intended substring to handle minor indexing drift
        window = max(len(original) + 12, 24)
        local_start = max(0, start_pos - window)
        local_end = min(len(stem_text), end_pos + window)
        local_view = stem_text[local_start:local_end]
        relative_idx = local_view.find(original)
        if relative_idx != -1:
            absolute_start = local_start + relative_idx
            return absolute_start, absolute_start + len(original)

        # Fall back to first occurrence from supplied start position onward
        fallback_idx = stem_text.find(original, start_pos)
        if fallback_idx != -1:
            return fallback_idx, fallback_idx + len(original)

        raise ValueError(
            f"Unable to align substring '{original}' within stem text for deterministic mapping"
        )

    def _compute_occurrence_index(self, stem_text: str, original: str, target_index: int) -> int:
        if not original:
            return 0
        occurrences: List[int] = []
        search_from = 0
        while True:
            idx = stem_text.find(original, search_from)
            if idx == -1:
                break
            occurrences.append(idx)
            search_from = idx + 1
        if not occurrences:
            return 0
        if target_index in occurrences:
            return occurrences.index(target_index)
        closest = min(occurrences, key=lambda val: abs(val - target_index))
        return occurrences.index(closest)

    def _recover_question_geometry(
        self,
        run_id: str,
        stem_text: str,
    ) -> Tuple[Optional[int], Optional[Tuple[float, float, float, float]]]:
        pdf_path = self._get_original_pdf_path(run_id)
        if not pdf_path or not pdf_path.exists():
            self.logger.error(
                "Unable to locate original PDF for run %s while recovering geometry",
                run_id,
            )
            return None, None

        try:
            doc = fitz.open(pdf_path)
        except Exception as exc:
            self.logger.error(
                "Failed to open PDF %s for run %s: %s",
                pdf_path,
                run_id,
                exc,
            )
            return None, None

        target = self.strip_zero_width(stem_text or "").replace("\n", " ").strip()
        snippet = target[: min(120, len(target))]

        try:
            for page_index, page in enumerate(doc):
                for needle in (target, snippet):
                    if not needle:
                        continue
                    try:
                        rects = page.search_for(needle)
                    except Exception:
                        rects = []
                    if rects:
                        rect = rects[0]
                        buffer = fitz.Rect(rect)
                        buffer.x0 -= 2
                        buffer.y0 -= 2
                        buffer.x1 += 2
                        buffer.y1 += 2
                        return page_index, (buffer.x0, buffer.y0, buffer.x1, buffer.y1)
        finally:
            doc.close()

        self.logger.warning(
            "Could not recover geometry for run %s question snippet '%s'",
            run_id,
            snippet,
        )
        return None, None

    def _get_original_pdf_path(self, run_id: str) -> Optional[Path]:
        structured = self.structured_manager.load(run_id)
        document_info = (structured or {}).get("document") or {}
        potential = document_info.get("source_path") or document_info.get("path")
        if potential:
            path = Path(str(potential))
            if path.exists():
                return path

        try:
            run = PipelineRun.query.get(run_id)
        except Exception as exc:
            self.logger.warning(
                "Unable to query pipeline run %s for original path: %s",
                run_id,
                exc,
            )
            return None

        if run and run.original_pdf_path:
            path = Path(run.original_pdf_path)
            if path.exists():
                return path

        return None

    def _group_contexts_by_page(
        self,
        mapping_context: Dict[str, List[Dict[str, object]]],
    ) -> Dict[int, List[Dict[str, object]]]:
        grouped: Dict[int, List[Dict[str, object]]] = defaultdict(list)
        for entries in (mapping_context or {}).values():
            for ctx in entries:
                page_idx = ctx.get("page")
                if not isinstance(page_idx, int):
                    continue
                grouped[page_idx].append(copy.deepcopy(ctx))
        for contexts in grouped.values():
            contexts.sort(
                key=lambda ctx: (
                    ctx.get("start_pos", float("inf")),
                    ctx.get("entry_index", 0),
                )
            )
        return grouped

    def _match_contexts_on_page(
        self,
        page: fitz.Page,
        contexts: List[Dict[str, object]],
        run_id: Optional[str],
    ) -> List[Dict[str, object]]:
        used_rects: List[fitz.Rect] = []
        used_fingerprints: set[str] = set()
        matches: List[Dict[str, object]] = []

        for ctx in contexts:
            probe = copy.deepcopy(ctx)
            location = self.locate_text_span(page, probe, used_rects, used_fingerprints)
            if not location:
                self.logger.warning(
                    "stream rewrite span not located",
                    extra={
                        "run_id": run_id,
                        "page": page.number,
                        "q_number": ctx.get("q_number"),
                        "original": ctx.get("original"),
                        "span_ids": ctx.get("stem_span_ids") or ctx.get("span_ids"),
                    },
                )
                continue
            rect, _, _ = location
            used_rects.append(rect)
            fingerprint_key = probe.get("matched_fingerprint_key")
            if fingerprint_key:
                used_fingerprints.add(str(fingerprint_key))
            if isinstance(rect, fitz.Rect):
                probe["available_width"] = rect.width
                probe["available_height"] = rect.height
                if not probe.get("selection_bbox"):
                    probe["selection_bbox"] = tuple(rect)
            matches.append(probe)

        return matches

    def _extract_text_segments(
        self,
        content: ContentStream,
        page: object,
    ) -> Tuple[List[Dict[str, object]], int, int]:
        segments: List[Dict[str, object]] = []
        tokens_scanned = 0
        tj_segments = 0
        current_offset = 0

        font_cmaps = self._build_font_cmaps(page)
        current_font: Optional[str] = None
        current_font_size: Optional[float] = None
        SPACE_THRESHOLD = -80.0

        for op_index, (operands, operator) in enumerate(content.operations):
            if operator == b"Tf" and len(operands) >= 2:
                font_name = operands[0]
                font_size = operands[1]
                if isinstance(font_name, NameObject):
                    current_font = str(font_name)
                # Extract font size - FloatObject/NumberObject can be converted to float
                try:
                    current_font_size = float(font_size)
                except (TypeError, ValueError, AttributeError):
                    pass
                continue

            if operator == b"Tj" and operands:
                tj_segments += 1
                text_obj = operands[0]
                decoded = self._decode_pdf_text(text_obj, current_font, font_cmaps)
                tokens_scanned += len(decoded)
                segments.append(
                    {
                        "index": op_index,
                        "operator": operator,
                        "operands": operands,
                        "text": decoded,
                        "original_text": decoded,
                        "start": current_offset,
                        "end": current_offset + len(decoded),
                        "kern_map": {},
                        "original_kern_map": {},
                        "modified": False,
                        "font_context": {
                            "font": current_font,
                            "fontsize": current_font_size,
                        },
                    }
                )
                current_offset += len(decoded)
                continue

            if operator == b"TJ" and operands:
                array_obj = operands[0]
                if not isinstance(array_obj, ArrayObject):
                    continue
                tj_segments += 1
                decoded_parts: List[str] = []
                kern_map: Dict[int, float] = {}
                relative_offset = 0
                for item in array_obj:
                    if isinstance(item, (TextStringObject, ByteStringObject)):
                        decoded_parts.append(self._decode_pdf_text(item, current_font, font_cmaps))
                        relative_offset += len(decoded_parts[-1])
                    elif isinstance(item, NumberObject):
                        try:
                            if float(item) <= SPACE_THRESHOLD:
                                decoded_parts.append(" ")
                                relative_offset += 1
                            kern_map[relative_offset] = kern_map.get(relative_offset, 0.0) + float(item)
                        except Exception:
                            pass
                decoded = "".join(decoded_parts)
                tokens_scanned += len(decoded)
                segments.append(
                    {
                        "index": op_index,
                        "operator": operator,
                        "operands": operands,
                        "text": decoded,
                        "original_text": decoded,
                        "start": current_offset,
                        "end": current_offset + len(decoded),
                        "kern_map": kern_map,
                        "original_kern_map": dict(kern_map),
                        "modified": False,
                        "font_context": {
                            "font": current_font,
                            "fontsize": current_font_size,
                        },
                    }
                )
                current_offset += len(decoded)

        return segments, tokens_scanned, tj_segments

    def _decode_pdf_text(
        self,
        text_obj: object,
        current_font: Optional[str],
        font_cmaps: Dict[str, Dict[str, object]],
    ) -> str:
        if isinstance(text_obj, TextStringObject):
            return str(text_obj)
        if isinstance(text_obj, ByteStringObject):
            return self._decode_with_cmap(bytes(text_obj), current_font, font_cmaps)
        return ""

    def _attach_stream_ranges_from_geometry(
        self,
        doc_page: fitz.Page,
        segments: List[Dict[str, object]],
        contexts: List[Dict[str, object]],
    ) -> None:
        geometry_contexts = [ctx for ctx in contexts if ctx.get("matched_glyph_path")]
        if not geometry_contexts or not segments:
            return

        raw = doc_page.get_text("rawdict") or {}
        blocks = raw.get("blocks") or []
        if not blocks:
            return

        combined_text = "".join(segment.get("text", "") for segment in segments)
        if not combined_text:
            return

        span_positions: Dict[Tuple[int, int, int], Dict[str, object]] = {}
        raw_parts: List[str] = []
        raw_index = 0

        for block_index, block in enumerate(blocks):
            for line_index, line in enumerate(block.get("lines", [])):
                for span_index, span in enumerate(line.get("spans", [])):
                    chars = span.get("chars", []) or []
                    if not chars:
                        continue

                    cursor = raw_index
                    char_positions: List[int] = [cursor]
                    char_origins: List[float] = []

                    for char_info in chars:
                        glyph = str(char_info.get("c", ""))
                        if glyph == "":
                            glyph = "\u0000"
                        raw_parts.append(glyph)
                        cursor += len(glyph)
                        char_positions.append(cursor)
                        origin = char_info.get("origin")
                        if isinstance(origin, (list, tuple)) and len(origin) >= 1:
                            try:
                                char_origins.append(float(origin[0]))
                            except (TypeError, ValueError):
                                char_origins.append(char_origins[-1] if char_origins else 0.0)
                        else:
                            char_origins.append(char_origins[-1] if char_origins else 0.0)

                    span_positions[(block_index, line_index, span_index)] = {
                        "positions": char_positions,
                        "origins": char_origins,
                        "font": span.get("font"),
                        "fontsize": span.get("size"),
                    }
                    raw_index = cursor

        if not raw_parts:
            return

        raw_string = "".join(raw_parts)
        matcher = difflib.SequenceMatcher(None, raw_string, combined_text, autojunk=False)
        alignment: Dict[int, int] = {}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "equal":
                continue
            for offset in range(i2 - i1):
                alignment[i1 + offset] = j1 + offset

        if not alignment:
            return

        for ctx in geometry_contexts:
            glyph_paths_raw = ctx.get("matched_glyph_paths")
            glyph_paths: List[Dict[str, object]] = []
            if isinstance(glyph_paths_raw, list):
                glyph_paths.extend(path for path in glyph_paths_raw if isinstance(path, dict))
            single_path = ctx.get("matched_glyph_path")
            if isinstance(single_path, dict) and single_path not in glyph_paths:
                glyph_paths.append(single_path)

            if not glyph_paths:
                continue

            aggregated_start: Optional[int] = None
            aggregated_end: Optional[int] = None
            chosen_origin: Optional[float] = None
            font_hint: Optional[str] = None
            fontsize_hint: Optional[float] = None

            for glyph_path in glyph_paths:
                block_idx = glyph_path.get("block")
                line_idx = glyph_path.get("line")
                span_idx = glyph_path.get("span")
                char_start = glyph_path.get("char_start")
                char_end = glyph_path.get("char_end")

                if None in (block_idx, line_idx, span_idx, char_start, char_end):
                    continue

                span_key = (int(block_idx), int(line_idx), int(span_idx))
                span_data = span_positions.get(span_key)
                if not span_data:
                    continue

                positions: List[int] = span_data.get("positions") or []
                origins: List[float] = span_data.get("origins") or []
                if len(positions) < 2:
                    continue

                char_count = len(positions) - 1
                if char_count <= 0:
                    continue

                char_start = max(0, min(int(char_start), char_count - 1))
                char_end = max(0, min(int(char_end), char_count))
                if char_end <= char_start:
                    continue

                raw_start = positions[char_start]
                raw_end = positions[char_end]
                path_origin = None
                if origins and char_start < len(origins):
                    path_origin = origins[char_start]

                mapped_start = None
                for raw_idx in range(raw_start, raw_end):
                    if raw_idx in alignment:
                        mapped_start = alignment[raw_idx]
                        break

                if mapped_start is None:
                    continue

                mapped_end = None
                for raw_idx in range(raw_end - 1, raw_start - 1, -1):
                    if raw_idx in alignment:
                        mapped_end = alignment[raw_idx] + 1
                        break

                if mapped_end is None or mapped_end <= mapped_start:
                    continue

                aggregated_start = mapped_start if aggregated_start is None else min(aggregated_start, mapped_start)
                aggregated_end = mapped_end if aggregated_end is None else max(aggregated_end, mapped_end)
                if chosen_origin is None and path_origin is not None:
                    chosen_origin = float(path_origin)
                if font_hint is None and span_data.get("font"):
                    font_hint = span_data.get("font")
                if fontsize_hint is None and span_data.get("fontsize"):
                    try:
                        fontsize_hint = float(span_data.get("fontsize"))
                    except (TypeError, ValueError):
                        fontsize_hint = None

            if aggregated_start is None or aggregated_end is None or aggregated_end <= aggregated_start:
                continue

            expected_raw = str(ctx.get("matched_text") or ctx.get("original") or "")
            expected_clean = self.strip_zero_width(expected_raw)

            def matches_range(start_idx: int, end_idx: int) -> bool:
                if start_idx < 0 or end_idx > len(combined_text) or end_idx <= start_idx:
                    return False
                candidate = combined_text[start_idx:end_idx]
                candidate_clean = self.strip_zero_width(candidate)
                if candidate_clean == expected_clean:
                    return True
                return self._compact_text(candidate_clean.casefold()) == self._compact_text(expected_clean.casefold())

            if expected_clean:
                if not matches_range(aggregated_start, aggregated_end):
                    if len(expected_raw):
                        aggregated_end = min(len(combined_text), aggregated_start + len(expected_raw))

                    if not matches_range(aggregated_start, aggregated_end):
                        for shift in range(1, 8):
                            start_candidate = aggregated_start - shift
                            end_candidate = start_candidate + len(expected_raw)
                            if end_candidate > len(combined_text):
                                continue
                            if matches_range(start_candidate, end_candidate):
                                aggregated_start = start_candidate
                                aggregated_end = end_candidate
                                break

                    if not matches_range(aggregated_start, aggregated_end):
                        window_start = max(0, aggregated_start - 50)
                        window_end = min(len(combined_text), aggregated_end + 50)
                        found_idx = combined_text.find(expected_raw, window_start, window_end)
                        if found_idx != -1:
                            aggregated_start = found_idx
                            aggregated_end = min(len(combined_text), found_idx + len(expected_raw))

                if not matches_range(aggregated_start, aggregated_end):
                    continue

            if not self._context_matches_surroundings(combined_text, aggregated_start, aggregated_end, ctx):
                continue

            ctx["stream_range"] = (aggregated_start, aggregated_end)
            ctx["stream_text"] = combined_text[aggregated_start:aggregated_end]
            if chosen_origin is not None:
                ctx["stream_start_origin"] = float(chosen_origin)
            if font_hint:
                ctx.setdefault("matched_font", font_hint)
            if fontsize_hint is not None:
                ctx.setdefault("matched_fontsize", fontsize_hint)

    def _plan_replacements(
        self,
        segments: List[Dict[str, object]],
        contexts: List[Dict[str, object]],
        used_fingerprints: set[str],
        run_id: Optional[str],
        page_index: int,
        doc_page: fitz.Page,
    ) -> List[Dict[str, object]]:
        combined_text = "".join(segment["text"] for segment in segments)
        replacements: List[Dict[str, object]] = []
        used_ranges: List[Tuple[int, int]] = []
        local_fingerprints: set[str] = set()

        def range_conflicts(candidate: Tuple[int, int]) -> bool:
            start, end = candidate
            for used_start, used_end in used_ranges:
                if start < used_end and end > used_start:
                    return True
            return False

        for ctx in contexts:
            fingerprint_key = str(ctx.get("matched_fingerprint_key") or ctx.get("fingerprint_key") or "")
            if fingerprint_key and fingerprint_key in used_fingerprints:
                continue
            if fingerprint_key and fingerprint_key in local_fingerprints:
                continue

            replacement_text = ctx.get("replacement")
            if not replacement_text:
                continue

            span: Optional[Tuple[int, int]] = None
            stream_range = ctx.get("stream_range")
            if stream_range and len(stream_range) == 2:
                try:
                    start_candidate = max(0, int(stream_range[0]))
                    end_candidate = max(start_candidate, int(stream_range[1]))
                except (TypeError, ValueError):
                    start_candidate = 0
                    end_candidate = 0
                end_candidate = min(end_candidate, len(combined_text))
                if end_candidate > start_candidate and not range_conflicts((start_candidate, end_candidate)):
                    candidate_text = combined_text[start_candidate:end_candidate]
                    candidate_clean = self.strip_zero_width(candidate_text)
                    stream_text_clean = self.strip_zero_width(str(ctx.get("stream_text") or ""))
                    original_clean = self.strip_zero_width(str(ctx.get("original") or ""))
                    reference_clean = stream_text_clean or original_clean
                    if reference_clean and candidate_clean != reference_clean:
                        span = None
                    elif self._context_matches_surroundings(combined_text, start_candidate, end_candidate, ctx):
                        span = (start_candidate, end_candidate)
                        if not ctx.get("stream_text"):
                            ctx["stream_text"] = candidate_text
                    else:
                        span = None

            if span is None:
                target_text = ctx.get("matched_text") or ctx.get("original")
                if not target_text:
                    continue
                span = self._find_match_position_in_combined_text(
                    combined_text,
                    str(target_text),
                    ctx,
                    used_ranges,
                )
                if not span:
                    self.logger.warning(
                        "stream rewrite text span not found",
                        extra={
                            "run_id": run_id,
                            "page": page_index,
                            "q_number": ctx.get("q_number"),
                            "original": ctx.get("original"),
                        },
                    )
                    continue

            start, end = span
            if end <= start:
                continue

            observed_text = combined_text[start:end]
            observed_clean = self.strip_zero_width(observed_text)
            expected_clean = self.strip_zero_width(str(ctx.get("matched_text") or ctx.get("original") or ""))
            if expected_clean and observed_clean != expected_clean:
                observed_compact = self._compact_text(observed_clean.casefold())
                expected_compact = self._compact_text(expected_clean.casefold())
                if not observed_compact or observed_compact != expected_compact:
                    self.logger.warning(
                        "stream rewrite span mismatch",
                        extra={
                            "run_id": run_id,
                            "page": page_index,
                            "q_number": ctx.get("q_number"),
                            "original": ctx.get("original"),
                            "observed": observed_text,
                        },
                    )
                    continue

            ctx["matched_text"] = observed_text

            if fingerprint_key:
                used_fingerprints.add(fingerprint_key)
                local_fingerprints.add(fingerprint_key)

            used_ranges.append((start, end))

            replacements.append(
                {
                    "start": start,
                    "end": end,
                    "replacement": replacement_text,
                    "context": ctx,
                    "fingerprint_key": fingerprint_key,
                    "applied": False,
                }
            )

        return replacements

    def _context_matches_surroundings(
        self,
        combined_text: str,
        start: int,
        end: int,
        context: Dict[str, object],
    ) -> bool:
        if start < 0 or end > len(combined_text) or end <= start:
            return False

        expected_prefix = self.strip_zero_width(str(context.get("prefix") or ""))
        expected_suffix = self.strip_zero_width(str(context.get("suffix") or ""))

        prefix_ok = True
        if expected_prefix:
            actual_prefix = self.strip_zero_width(
                combined_text[max(0, start - len(expected_prefix)) : start]
            )
            actual_norm = self._normalize_for_compare(actual_prefix)
            expected_norm = self._normalize_for_compare(expected_prefix)
            if expected_norm:
                actual_compact = self._compact_text(actual_norm)
                expected_compact = self._compact_text(expected_norm)
                if expected_compact:
                    prefix_ok = actual_compact.endswith(expected_compact)

        suffix_ok = True
        if expected_suffix:
            actual_suffix = self.strip_zero_width(
                combined_text[end : end + len(expected_suffix)]
            )
            actual_norm = self._normalize_for_compare(actual_suffix)
            expected_norm = self._normalize_for_compare(expected_suffix)
            if expected_norm:
                actual_compact = self._compact_text(actual_norm)
                expected_compact = self._compact_text(expected_norm)
                if expected_compact:
                    suffix_ok = actual_compact.startswith(expected_compact)

        if expected_prefix and not prefix_ok:
            return False
        if not expected_prefix and expected_suffix and not suffix_ok:
            return False
        return True

    def _find_match_position_in_combined_text(
        self,
        combined_text: str,
        target_text: str,
        context: Dict[str, object],
        used_ranges: List[Tuple[int, int]],
    ) -> Optional[Tuple[int, int]]:
        if not target_text:
            return None

        expected_prefix = self.strip_zero_width(str(context.get("prefix") or ""))
        expected_suffix = self.strip_zero_width(str(context.get("suffix") or ""))
        occurrence_expected = context.get("occurrence_index")

        search_start = 0
        occurrence_counter = 0

        while True:
            idx = combined_text.find(target_text, search_start)
            if idx == -1:
                break
            end = idx + len(target_text)

            if any(not (end <= start or idx >= finish) for start, finish in used_ranges):
                search_start = idx + 1
                continue

            if not self._context_matches_surroundings(combined_text, idx, end, context):
                search_start = idx + 1
                continue

            if occurrence_expected is None or occurrence_counter == occurrence_expected:
                return idx, end
            occurrence_counter += 1
            search_start = idx + 1

        normalized_target = self.strip_zero_width(target_text)
        compact_target = self._compact_text(normalized_target.casefold())
        if compact_target:
            combined_lower = combined_text.casefold()
            compact_chars: List[str] = []
            index_map: List[int] = []
            for idx, ch in enumerate(combined_lower):
                if ch.isalnum():
                    compact_chars.append(ch)
                    index_map.append(idx)
            compact_source = "".join(compact_chars)
            search_pos = 0
            while True:
                idx_compact = compact_source.find(compact_target, search_pos)
                if idx_compact == -1:
                    break
                if idx_compact + len(compact_target) - 1 >= len(index_map):
                    break
                start_orig = index_map[idx_compact]
                end_orig = index_map[idx_compact + len(compact_target) - 1] + 1
                if any(not (end_orig <= start or start_orig >= finish) for start, finish in used_ranges):
                    search_pos = idx_compact + 1
                    continue
                if not self._context_matches_surroundings(combined_text, start_orig, end_orig, context):
                    search_pos = idx_compact + 1
                    continue
                if occurrence_expected is None or occurrence_counter == occurrence_expected:
                    return start_orig, end_orig
                occurrence_counter += 1
                search_pos = idx_compact + 1

        return None

    def _apply_segment_edits(
        self,
        segments: List[Dict[str, object]],
        replacements: List[Dict[str, object]],
        run_id: Optional[str],
        page_index: int,
        doc_page: fitz.Page,
    ) -> bool:
        segment_map = {id(seg): seg for seg in segments}
        edits_by_segment: Dict[int, List[Tuple[int, int, str]]] = defaultdict(list)
        modified = False

        for replacement in replacements:
            start = int(replacement.get("start", 0))
            end = int(replacement.get("end", 0))
            insert_text = str(replacement.get("replacement") or "")

            covering_segments = [
                seg for seg in segments if seg["start"] < end and seg["end"] > start
            ]
            if not covering_segments:
                self.logger.warning(
                    "stream rewrite found no covering segment",
                    extra={
                        "run_id": run_id,
                        "page": page_index,
                        "start": start,
                        "end": end,
                    },
                )
                continue

            replacement.setdefault("operator_index", covering_segments[0].get("index"))

            inserted = False
            for seg in covering_segments:
                seg_start = seg["start"]
                seg_end = seg["end"]
                local_start = max(start, seg_start) - seg_start
                local_end = min(end, seg_end) - seg_start
                if local_end < local_start:
                    continue

                text_to_insert = insert_text if not inserted else ""
                edits_by_segment[id(seg)].append((local_start, local_end, text_to_insert))
                inserted = True

            if not inserted:
                self.logger.warning(
                    "stream rewrite could not queue edit for segment",
                    extra={
                        "run_id": run_id,
                        "page": page_index,
                        "start": start,
                        "end": end,
                    },
                )
                continue

            replacement["_queued_for_segment"] = True

        for seg_id, edits in edits_by_segment.items():
            segment = segment_map.get(seg_id)
            if not segment:
                continue
            text = segment.get("text", "")
            edits.sort(key=lambda item: item[0])
            cursor = 0
            new_text_parts: List[str] = []
            for local_start, local_end, insert_text in edits:
                new_text_parts.append(text[cursor:local_start])
                new_text_parts.append(insert_text)
                cursor = local_end
            new_text_parts.append(text[cursor:])
            new_text = "".join(new_text_parts)
            if new_text != text:
                segment["new_text"] = new_text
                modified = True

        return modified

    def _capture_span_plan_entries(
        self,
        span_plan_capture: Optional[Dict[int, List["SpanRewriteEntry"]]],
        page_index: int,
        replacements: List[Dict[str, object]],
        doc_page: fitz.Page,
    ) -> None:
        if span_plan_capture is None:
            return

        try:
            from .span_rewrite_plan import SpanMappingRef, SpanRewriteEntry
        except Exception:
            return

        page_entries = span_plan_capture.setdefault(page_index, [])

        for replacement in replacements:
            if not replacement.get("applied"):
                continue

            ctx = replacement.get("context") or {}
            if not isinstance(ctx, dict):
                ctx = {}

            original_text = str(ctx.get("matched_text") or ctx.get("original") or "")
            replacement_text = str(replacement.get("replacement") or ctx.get("replacement") or "")

            glyph_path = ctx.get("matched_glyph_path") or {}

            def to_int(value, default: int = -1) -> int:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            block_index = to_int(glyph_path.get("block"))
            line_index = to_int(glyph_path.get("line"))
            span_index = to_int(glyph_path.get("span"))

            bbox_source = (
                ctx.get("matched_rect")
                or ctx.get("selection_bbox")
                or ctx.get("bbox")
            )
            bbox: Tuple[float, float, float, float]
            if isinstance(bbox_source, (list, tuple)) and len(bbox_source) == 4:
                try:
                    bbox = tuple(float(v) for v in bbox_source)  # type: ignore[assignment]
                except (TypeError, ValueError):
                    bbox = (0.0, 0.0, 0.0, 0.0)
            else:
                bbox = (0.0, 0.0, 0.0, 0.0)

            font_name = ctx.get("matched_font")
            try:
                font_size = float(ctx.get("matched_fontsize") or 0.0)
            except (TypeError, ValueError):
                font_size = 0.0

            original_width = ctx.get("matched_rect_width")
            try:
                original_width = float(original_width) if original_width is not None else None
            except (TypeError, ValueError):
                original_width = None
            if original_width is None:
                original_width = self._measure_text_width(doc_page, original_text, font_name, font_size)

            replacement_width = self._measure_text_width(doc_page, replacement_text, font_name, font_size)

            scale_factor = 1.0
            if original_width and replacement_width and replacement_width > original_width:
                scale_factor = max(original_width / replacement_width, 0.01)

            mapping_ref = SpanMappingRef(
                q_number=str(ctx.get("q_number") or ""),
                original=original_text,
                replacement=replacement_text,
                context_index=ctx.get("entry_index"),
                start=int(replacement.get("start") or 0),
                end=int(replacement.get("end") or 0),
                operator_index=replacement.get("operator_index"),
            )

            slice_record = {
                "normalized_start": 0,
                "normalized_end": len(original_text),
                "raw_start": 0,
                "raw_end": len(original_text),
                "replacement_text": replacement_text,
            }

            entry = SpanRewriteEntry(
                page_index=page_index,
                block_index=block_index,
                line_index=line_index,
                span_index=span_index,
                operator_index=replacement.get("operator_index"),
                original_text=original_text,
                replacement_text=replacement_text,
                font=font_name,
                font_size=float(font_size or 0.0),
                bbox=bbox,
                matrix=(1.0, 0.0, 0.0, 1.0, float(bbox[0]), float(bbox[1])),
                original_width=float(original_width or 0.0),
                replacement_width=float(replacement_width or 0.0),
                scale_factor=float(scale_factor),
                mappings=[mapping_ref],
                fragment_rewrites=[],
                slice_replacements=[slice_record],
                overlay_fallback=False,
                requires_scaling=scale_factor < 0.999,
                validation_failures=[],
            )

            page_entries.append(entry)

    def _measure_text_width(
        self,
        doc_page: Optional[fitz.Page],
        text: str,
        font_name: Optional[str],
        font_size: float,
    ) -> float:
        if not text:
            return 0.0
        if doc_page is not None and font_name and font_size > 0:
            try:
                return float(doc_page.get_text_length(text, fontname=font_name, fontsize=float(font_size)))
            except Exception:
                pass
        if font_size > 0:
            return float(len(text)) * float(font_size)
        return float(len(text))

    def _rebuild_operations(
        self,
        operations: List[Tuple[List[object], bytes]],
        segments: List[Dict[str, object]],
    ) -> List[Tuple[List[object], bytes]]:
        segments_by_index = {seg["index"]: seg for seg in segments}
        updated: List[Tuple[List[object], bytes]] = []

        for idx, (operands, operator) in enumerate(operations):
            segment = segments_by_index.get(idx)
            if not segment:
                updated.append((operands, operator))
                continue

            scale = float(segment.get("scale", 1.0))
            modified = bool(segment.get("modified"))

            if not modified and scale >= 0.995:
                updated.append((operands, operator))
                continue

            if scale < 0.995:
                updated.append(([NumberObject(round(scale * 100, 4))], b"Tz"))

            if modified:
                text_value = segment.get("text") or ""
                kern_map = dict(segment.get("kern_map") or {})
                pieces: List[Tuple[str, object]] = []
                cursor = 0
                for pos in sorted(kern_map.keys()):
                    pos_clamped = max(0, min(int(pos), len(text_value)))
                    if pos_clamped > cursor:
                        pieces.append(("text", text_value[cursor:pos_clamped]))
                    value = float(kern_map[pos])
                    if abs(value) >= 0.001:
                        pieces.append(("kern", round(value, 6)))
                    cursor = pos_clamped
                if cursor < len(text_value):
                    pieces.append(("text", text_value[cursor:]))
                if not pieces:
                    pieces.append(("text", ""))

                has_kern = any(kind == "kern" for kind, _ in pieces)
                if (
                    not has_kern
                    and len(pieces) == 1
                    and pieces[0][0] == "text"
                    and operator == b"Tj"
                    and not segment.get("original_kern_map")
                ):
                    updated.append(([TextStringObject(pieces[0][1])], b"Tj"))
                else:
                    array = ArrayObject()
                    for kind, value in pieces:
                        if kind == "text":
                            array.append(TextStringObject(value))
                        else:
                            array.append(NumberObject(value))
                    updated.append(([array], b"TJ"))
            else:
                updated.append((operands, operator))

            if scale < 0.995:
                updated.append(([NumberObject(100)], b"Tz"))

        return updated

    def _build_font_cmaps(self, page) -> Dict[str, Dict[str, object]]:
        cmaps: Dict[str, Dict[str, object]] = {}
        try:
            resources = page.get("/Resources") or {}
            fonts = resources.get("/Font") or {}
            for font_key, font_obj in (fonts.items() if hasattr(fonts, "items") else []):
                try:
                    font = font_obj.get_object() if hasattr(font_obj, "get_object") else font_obj
                    to_unicode = font.get("/ToUnicode") if isinstance(font, dict) else None
                    if to_unicode is None:
                        continue
                    stream = to_unicode.get_data() if hasattr(to_unicode, "get_data") else bytes(to_unicode)
                    cmap_map, _, _ = self._parse_tounicode_cmap(stream)
                    if cmap_map:
                        cmaps[str(font_key)] = cmap_map
                except Exception:
                    continue
        except Exception:
            pass
        return cmaps

    def _parse_tounicode_cmap(self, stream: bytes) -> Tuple[Dict[str, str], int, int]:
        cmap: Dict[str, str] = {}
        min_len = 1
        max_len = 1

        try:
            text = stream.decode("utf-16-be", errors="ignore")
        except Exception:
            text = stream.decode("latin-1", errors="ignore")

        import re

        bfchar_pattern = re.compile(r"beginbfchar(.*?)endbfchar", re.S)
        bfrange_pattern = re.compile(r"beginbfrange(.*?)endbfrange", re.S)

        for bfchar_block in bfchar_pattern.findall(text):
            lines = bfchar_block.strip().splitlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    src = parts[0].strip("<>")
                    dst = parts[1].strip("<>")
                    cmap[src] = bytes.fromhex(dst).decode("utf-16-be", errors="ignore")
                    min_len = min(min_len, len(src) // 2)
                    max_len = max(max_len, len(src) // 2)

        for bfrange_block in bfrange_pattern.findall(text):
            lines = bfrange_block.strip().splitlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 3:
                    start = int(parts[0].strip("<>") or "0", 16)
                    end = int(parts[1].strip("<>") or "0", 16)
                    dest = parts[2]
                    if dest.startswith("<"):
                        base = int(dest.strip("<>") or "0", 16)
                        for offset, cid in enumerate(range(start, end + 1)):
                            code = format(cid, "04X")
                            char = bytes.fromhex(format(base + offset, "04X")).decode(
                                "utf-16-be", errors="ignore"
                            )
                            cmap[code] = char
                    elif dest.startswith("["):
                        entries = [entry.strip("<>") for entry in dest.strip("[]").split()]
                        for cid, entry in zip(range(start, end + 1), entries):
                            code = format(cid, "04X")
                            char = bytes.fromhex(entry).decode("utf-16-be", errors="ignore")
                            cmap[code] = char
        return cmap, min_len, max_len

    def _decode_with_cmap(
        self,
        data: bytes,
        current_font: Optional[str],
        font_cmaps: Dict[str, Dict[str, object]],
    ) -> str:
        if not data:
            return ""
        if current_font and current_font in font_cmaps:
            cmap = font_cmaps[current_font]
            hex_data = data.hex().upper()
            i = 0
            result: List[str] = []
            while i < len(hex_data):
                for length in range(4, 0, -1):
                    chunk = hex_data[i : i + length * 2]
                    if chunk in cmap:
                        result.append(cmap[chunk])
                        i += length * 2
                        break
                else:
                    try:
                        result.append(bytes.fromhex(hex_data[i : i + 2]).decode("latin-1"))
                    except Exception:
                        pass
                    i += 2
            return "".join(result)
        try:
            return data.decode("utf-16-be")
        except Exception:
            try:
                return data.decode("utf-8")
            except Exception:
                return data.decode("latin-1", errors="ignore")

    def rewrite_content_streams_structured(
        self,
        pdf_bytes: bytes,
        mapping: Dict[str, str],
        mapping_context: Dict[str, List[Dict[str, object]]],
        run_id: Optional[str] = None,
        original_pdf_path: Optional[Path] = None,
        span_plan_capture: Optional[Dict[int, List["SpanRewriteEntry"]]] = None,
    ) -> Tuple[bytes, Dict[str, int]]:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        contexts_by_page = self._group_contexts_by_page(mapping_context)
        used_fingerprints: set[str] = set()

        if span_plan_capture is not None:
            span_plan_capture.clear()

        total_pages = len(reader.pages)
        tokens_scanned = 0
        tj_segments = 0
        replacements_applied = 0
        matches_found = 0

        for page_index, page in enumerate(reader.pages):
            page_contexts = contexts_by_page.get(page_index, [])
            if not page_contexts:
                writer.add_page(page)
                continue

            matched_contexts = self._match_contexts_on_page(
                doc[page_index],
                page_contexts,
                run_id,
            )

            if not matched_contexts:
                writer.add_page(page)
                continue

            content = ContentStream(page.get_contents(), reader)
            segments, tokens, tj_hits = self._extract_text_segments(content, page)
            tokens_scanned += tokens
            tj_segments += tj_hits

            try:
                self._attach_stream_ranges_from_geometry(
                    doc[page_index],
                    segments,
                    matched_contexts,
                )
            except Exception:
                self.logger.exception(
                    "Failed to align geometry to stream on page %s",
                    page_index,
                )

            replacements = self._plan_replacements(
                segments,
                matched_contexts,
                used_fingerprints,
                run_id,
                page_index,
                doc[page_index],
            )

            if not replacements:
                writer.add_page(page)
                continue

            modified = self._apply_segment_edits(
                segments,
                replacements,
                run_id,
                page_index,
                doc[page_index],
            )

            if modified:
                matches_found += len(replacements)

                # Use new Courier font strategy instead of old reconstruction
                self.logger.info(
                    f"DEBUG: About to apply Courier font strategy",
                    extra={
                        "run_id": run_id,
                        "page": page_index,
                        "num_operations": len(content.operations),
                        "num_segments": len(segments),
                        "num_replacements": len(replacements)
                    },
                )

                try:
                    # Save operations before transformation
                    operations_before = content.operations.copy()

                    content.operations = self._rebuild_operations_with_courier_font(
                        content.operations, segments, replacements, run_id
                    )

                    # Save operations after transformation
                    operations_after = content.operations.copy()

                    self.logger.info(
                        f"DEBUG: Courier font strategy completed successfully",
                        extra={"run_id": run_id, "page": page_index},
                    )

                    # Save enhanced debug output with full page hierarchy
                    if original_pdf_path and original_pdf_path.exists():
                        try:
                            # Extract font context from segments
                            font_context_summary = {}
                            for seg in segments:
                                fc = seg.get('font_context', {})
                                if fc.get('font'):
                                    font_context_summary[seg['index']] = {
                                        'font': fc.get('font'),
                                        'fontsize': fc.get('fontsize'),
                                        'text_preview': seg.get('text', '')[:50]
                                    }

                            self._save_enhanced_debug(
                                run_id=run_id,
                                stage=f"page_{page_index}_rewrite",
                                original_pdf_path=original_pdf_path,
                                page_index=page_index,
                                operations_before=operations_before,
                                operations_after=operations_after,
                                font_context=font_context_summary
                            )
                        except Exception as debug_exc:
                            self.logger.warning(
                                f"Enhanced debug save failed: {debug_exc}",
                                extra={"run_id": run_id, "page": page_index}
                            )

                except Exception as exc:
                    # Fallback to original method if new approach fails
                    self.logger.warning(
                        "Courier font strategy failed, falling back to original method",
                        extra={"run_id": run_id, "page": page_index, "error": str(exc)},
                    )
                    content.operations = self._rebuild_operations(content.operations, segments)
                    for replacement in replacements:
                        if replacement.get("_queued_for_segment"):
                            replacement["applied"] = True

                finally:
                    if span_plan_capture is not None:
                        try:
                            self._capture_span_plan_entries(
                                span_plan_capture,
                                page_index,
                                replacements,
                                doc[page_index],
                            )
                        except Exception:
                            self.logger.exception(
                                "failed to record span plan entries",
                                extra={"run_id": run_id, "page": page_index},
                            )

                    replacements_applied += sum(1 for item in replacements if item.get("applied"))

                page[NameObject("/Contents")] = content

            writer.add_page(page)

        doc.close()

        buffer = io.BytesIO()
        writer.write(buffer)

        return buffer.getvalue(), {
            "pages": total_pages,
            "tj_hits": tj_segments,
            "replacements": replacements_applied,
            "matches_found": matches_found,
            "tokens_scanned": tokens_scanned,
        }

    def validate_output_with_context(
        self,
        pdf_bytes: bytes,
        mapping_context: Dict[str, List[Dict[str, object]]],
        run_id: Optional[str] = None,
    ) -> None:
        if not mapping_context:
            return

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            errors: List[str] = []
            for entries in mapping_context.values():
                for ctx in entries:
                    page_idx = ctx.get("page")
                    bbox = ctx.get("selection_bbox") or ctx.get("stem_bbox") or ctx.get("bbox")
                    if not isinstance(page_idx, int):
                        continue

                    try:
                        rect = fitz.Rect(*bbox) if bbox and len(bbox) == 4 else None
                    except Exception:
                        rect = None

                    if page_idx < 0 or page_idx >= len(doc):
                        continue

                    page = doc[page_idx]
                    selection_quads = ctx.get("selection_quads") or []
                    texts: List[str] = []
                    if selection_quads:
                        for quad in selection_quads:
                            try:
                                quad_rect = fitz.Quad(quad).rect
                            except Exception:
                                continue
                            expanded = fitz.Rect(quad_rect)
                            expanded.x0 -= 1
                            expanded.y0 -= 1
                            expanded.x1 += 1
                            expanded.y1 += 1
                            overflow_left = float(ctx.get("rewrite_left_overflow") or 0.0)
                            overflow_right = float(ctx.get("rewrite_right_overflow") or 0.0)
                            if overflow_left:
                                expanded.x0 -= overflow_left
                            if overflow_right:
                                expanded.x1 += overflow_right
                            texts.append(page.get_text("text", clip=expanded) or "")
                        region_text = " ".join(texts)
                    elif rect is not None:
                        expanded = fitz.Rect(rect)
                        expanded.x0 -= 10
                        expanded.y0 -= 10
                        expanded.x1 += 10
                        expanded.y1 += 10
                        overflow_left = float(ctx.get("rewrite_left_overflow") or 0.0)
                        overflow_right = float(ctx.get("rewrite_right_overflow") or 0.0)
                        if overflow_left:
                            expanded.x0 -= overflow_left
                        if overflow_right:
                            expanded.x1 += overflow_right
                        region_text = page.get_text("text", clip=expanded) or ""
                    else:
                        continue
                    normalized = self.strip_zero_width(region_text).strip()
                    normalized_lower = normalized.casefold()

                    original = self.strip_zero_width(str(ctx.get("original") or "")).strip()
                    replacement = self.strip_zero_width(str(ctx.get("replacement") or "")).strip()

                    if original and original.casefold() in normalized_lower:
                        errors.append(
                            f"Original text still present on page {page_idx + 1} for Q{ctx.get('q_number')}: '{original}'"
                        )

                    if replacement:
                        count = normalized_lower.count(replacement.casefold())
                        if count != 1:
                            errors.append(
                                f"Replacement '{replacement}' occurs {count} times on page {page_idx + 1} (expected 1)"
                            )

            if errors:
                message = "; ".join(errors[:5])
                self.logger.error(
                    "post-render validation failed",
                    extra={"run_id": run_id, "errors": errors[:10]},
                )
                raise ValueError(message)
        finally:
            doc.close()

    def _encode_marker(self, context: str) -> str:
        digest = hashlib.sha1(context.encode("utf-8")).digest()
        marker_chars = [
            self._ZERO_WIDTH_MARKERS[digest[i] % len(self._ZERO_WIDTH_MARKERS)]
            for i in range(6)
        ]
        return "".join(marker_chars)

    def _split_multi_span(self, original: str, replacement: str) -> List[Tuple[str, str]]:
        originals = [segment.strip() for segment in re.split(r"(?:\r?\n)+", original) if segment.strip()]
        replacements = [segment.strip() for segment in re.split(r"(?:\r?\n)+", replacement) if segment.strip()]
        if not originals:
            return []
        if not replacements:
            replacements = originals.copy()
        while len(replacements) < len(originals):
            replacements.append(replacements[-1])
        if len(replacements) > len(originals):
            replacements = replacements[: len(originals)]
        return list(zip(originals, replacements))

    def expand_mapping_pairs(self, mapping: Dict[str, str]) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for key, value in (mapping or {}).items():
            clean_key = self.strip_zero_width(key)
            clean_value = self.strip_zero_width(value)
            if clean_key and clean_value:
                pairs.append((clean_key, clean_value))
        return pairs

    # === Text location helpers ==================================================

    def _find_occurrences(
        self,
        page: fitz.Page,
        needle: str,
        clip_rect: Optional[fitz.Rect] = None,
    ) -> List[Dict[str, object]]:
        results: List[Dict[str, object]] = []
        if not needle:
            return results

        needle_cf = needle.casefold()
        raw = page.get_text("rawdict") or {}
        blocks = raw.get("blocks") or []

        occurrence_counter = 0

        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_bbox = span.get("bbox")
                    if clip_rect and span_bbox and not fitz.Rect(*span_bbox).intersects(clip_rect):
                        continue

                    chars = span.get("chars", [])
                    if not chars:
                        continue
                    text = span.get("text")
                    if not text:
                        text = "".join(ch.get("c", "") for ch in chars)
                    if not text:
                        continue
                    lowered = text.casefold()
                    start = 0
                    while True:
                        idx = lowered.find(needle_cf, start)
                        if idx == -1:
                            break
                        end = idx + len(needle_cf)
                        if end > len(chars):
                            break
                        char_rect = fitz.Rect(chars[idx]["bbox"])
                        for ch in chars[idx + 1 : end]:
                            char_rect |= fitz.Rect(ch.get("bbox", char_rect))
                        if clip_rect and not char_rect.intersects(clip_rect):
                            start = end
                            continue
                        fontsize = float(span.get("size", 10.0))
                        span_len = end - idx
                        prefix = text[max(0, idx - 32) : idx]
                        suffix = text[end : end + 32]
                        results.append(
                            {
                                "rect": char_rect,
                                "fontsize": fontsize,
                                "span_len": span_len,
                                "prefix": prefix,
                                "suffix": suffix,
                                "text": text[idx:end],
                                "occurrence": occurrence_counter,
                            }
                        )
                        occurrence_counter += 1
                        start = end

        results.sort(
            key=lambda item: (
                round(item["rect"].y0, 3),
                round(item["rect"].x0, 3),
            )
        )
        return results

    def _rects_conflict(self, rect: fitz.Rect, used_rects: List[fitz.Rect]) -> bool:
        for used in used_rects:
            if rect.intersects(used):
                return True
        return False

    def _format_span_id(
        self,
        page_idx: int,
        block_idx: int,
        line_idx: int,
        span_idx: int,
    ) -> str:
        return f"page{page_idx}:block{block_idx}:line{line_idx}:span{span_idx}"

    def _get_span_records_for_page(self, page: fitz.Page) -> Dict[str, object]:
        page_idx = int(getattr(page, "number", 0))
        cached = self._span_record_cache.get(page_idx)
        if cached is not None:
            return cached

        records = collect_span_records(page, page_idx)
        span_map: Dict[str, object] = {}
        for record in records:
            span_id = self._format_span_id(
                page_idx,
                record.block_index,
                record.line_index,
                record.span_index,
            )
            span_map[span_id] = record
        self._span_record_cache[page_idx] = span_map
        return span_map

    def _order_span_ids(
        self,
        span_ids: Iterable[str],
        span_records: Dict[str, object],
    ) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        index_lookup: Dict[str, int] = {}
        for idx, span_id in enumerate(span_ids):
            sid = str(span_id)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            deduped.append(sid)
            index_lookup[sid] = idx

        def safe_int(val: object) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return 10**6

        def parse_components(value: str) -> Tuple[int, int, int]:
            try:
                parts = value.split(":")
                block_raw = parts[1].replace("block", "") if len(parts) > 1 else ""
                line_raw = parts[2].replace("line", "") if len(parts) > 2 else ""
                span_raw = parts[3].replace("span", "") if len(parts) > 3 else ""
                block_idx = safe_int(block_raw)
                line_idx = safe_int(line_raw)
                span_idx = safe_int(span_raw)
                return block_idx, line_idx, span_idx
            except Exception:
                return (10**6, 10**6, 10**6)

        def order_key(value: str) -> Tuple[int, int, int, int]:
            record = span_records.get(value)
            if record is not None:
                return (
                    safe_int(getattr(record, "block_index", 10**6)),
                    safe_int(getattr(record, "line_index", 10**6)),
                    safe_int(getattr(record, "span_index", 10**6)),
                    index_lookup.get(value, 0),
                )
            block_idx, line_idx, span_idx = parse_components(value)
            return (block_idx, line_idx, span_idx, index_lookup.get(value, 0))

        return sorted(deduped, key=order_key)

    def _normalized_to_raw_index(self, record: object, norm_index: int) -> int:
        try:
            mapping = getattr(record, "normalized_to_raw_indices", None)
        except AttributeError:
            mapping = None
        if mapping is None:
            return int(norm_index)
        if isinstance(mapping, dict):
            try:
                return int(mapping.get(int(norm_index), norm_index))
            except (TypeError, ValueError):
                return int(norm_index)
        cache = getattr(record, "_normalized_index_map", None)
        if cache is None:
            try:
                cache = {int(norm): int(raw) for norm, raw in mapping}
            except Exception:
                cache = {}
            setattr(record, "_normalized_index_map", cache)
        try:
            return int(cache.get(int(norm_index), norm_index))
        except (TypeError, ValueError):
            return int(norm_index)

    def _rect_from_record_slice(
        self,
        record: object,
        start_index: int,
        end_index: int,
    ) -> Optional[fitz.Rect]:
        normalized_chars = getattr(record, "normalized_chars", [])
        if not normalized_chars:
            return None
        clamped_start = max(0, min(int(start_index), len(normalized_chars)))
        clamped_end = max(clamped_start, min(int(end_index), len(normalized_chars)))
        if clamped_end <= clamped_start:
            return None

        rect: Optional[fitz.Rect] = None
        for idx in range(clamped_start, clamped_end):
            try:
                _, bbox = normalized_chars[idx]
            except (ValueError, TypeError):
                continue
            if not bbox:
                continue
            try:
                char_rect = fitz.Rect(*bbox)
            except Exception:
                continue
            if rect is None:
                rect = char_rect
            else:
                rect |= char_rect

        return rect

    def _locate_using_span_ids(
        self,
        page: fitz.Page,
        context: Dict[str, object],
        span_ids: object,
    ) -> Optional[Tuple[fitz.Rect, float, int]]:
        if not span_ids:
            return None

        if isinstance(span_ids, (list, tuple)):
            candidate_span_ids = [str(span_id) for span_id in span_ids if span_id]
        elif isinstance(span_ids, str):
            candidate_span_ids = [span_ids]
        else:
            return None

        if not candidate_span_ids:
            return None

        original_text = str(context.get("original") or "")
        target_normalized, _ = self._build_normalized_map(original_text)
        if not target_normalized:
            return None
        target_lower = target_normalized.lower()

        span_records = self._get_span_records_for_page(page)
        ordered_span_ids = self._order_span_ids(candidate_span_ids, span_records)

        if not ordered_span_ids:
            return None

        for span_id in ordered_span_ids:
            record = span_records.get(span_id)
            if not record:
                continue

            span_text_raw = getattr(record, "normalized_text", None)
            if span_text_raw is None:
                span_text_raw = getattr(record, "text", "")

            candidate_normalized, glyph_map = self._build_normalized_map(str(span_text_raw or ""))
            if not candidate_normalized or not glyph_map:
                continue

            candidate_lower = candidate_normalized.lower()
            index = candidate_lower.find(target_lower)
            if index == -1:
                continue

            end_norm_index = index + len(target_lower) - 1
            if end_norm_index >= len(glyph_map):
                end_norm_index = len(glyph_map) - 1
            glyph_start_norm = glyph_map[index]
            glyph_end_norm = glyph_map[end_norm_index] + 1

            rect = self._rect_from_record_slice(record, glyph_start_norm, glyph_end_norm)
            if rect is None:
                continue

            raw_start = self._normalized_to_raw_index(record, glyph_start_norm)
            raw_end = self._normalized_to_raw_index(record, glyph_end_norm - 1) + 1

            context["matched_rect"] = tuple(rect)
            context["matched_rect_width"] = float(rect.width)
            context["matched_font"] = getattr(record, "font", None)
            try:
                context["matched_fontsize"] = float(getattr(record, "font_size", 0.0) or 0.0)
            except (TypeError, ValueError):
                context["matched_fontsize"] = 0.0
            stripped_span = self.strip_zero_width(str(span_text_raw or ""))
            context["matched_span_len"] = glyph_end_norm - glyph_start_norm
            context["matched_text"] = stripped_span[glyph_start_norm:glyph_end_norm] or (
                original_text.strip() or target_normalized
            )
            context["matched_origin_x"] = float(rect.x0)
            context["matched_origin_y"] = float(rect.y0)
            context["matched_end_origin_x"] = float(rect.x1)
            context["matched_end_origin_y"] = float(rect.y1)
            glyph_path = {
                "block": getattr(record, "block_index", None),
                "line": getattr(record, "line_index", None),
                "span": getattr(record, "span_index", None),
                "char_start": raw_start,
                "char_end": raw_end,
                "norm_start": glyph_start_norm,
                "norm_end": glyph_end_norm,
                "span_id": span_id,
            }
            context["matched_glyph_path"] = glyph_path
            context["matched_glyph_paths"] = [glyph_path]
            context["matched_span_ids"] = [span_id]
            context.setdefault("span_ids", [span_id])
            context.setdefault("stem_span_ids", ordered_span_ids)

            fontsize = float(context.get("matched_fontsize") or 0.0) or 10.0
            return rect, fontsize, glyph_end_norm - glyph_start_norm

        if len(ordered_span_ids) > 1:
            combined_location = self._locate_across_span_sequence(
                context,
                ordered_span_ids,
                span_records,
                target_lower,
                original_text,
            )
            if combined_location:
                return combined_location

        return None

    def _locate_across_span_sequence(
        self,
        context: Dict[str, object],
        span_ids: List[str],
        span_records: Dict[str, object],
        target_lower: str,
        original_text: str,
    ) -> Optional[Tuple[fitz.Rect, float, int]]:
        combined_entries: List[Dict[str, object]] = []
        compact_chars: List[str] = []
        compact_map: List[int] = []

        for span_id in span_ids:
            record = span_records.get(span_id)
            if not record:
                continue
            raw_text = getattr(record, "normalized_text", None)
            if raw_text is None:
                raw_text = getattr(record, "text", "")
            normalized, glyph_map = self._build_normalized_map(str(raw_text or ""))
            if not normalized or not glyph_map:
                continue

            for idx, char in enumerate(normalized):
                glyph_index = glyph_map[idx]
                entry = {
                    "record": record,
                    "char": char,
                    "glyph_index": glyph_index,
                    "span_id": span_id,
                }
                combined_entries.append(entry)
                if char != " ":
                    compact_map.append(len(combined_entries) - 1)
                    compact_chars.append(char)

        if not combined_entries:
            return None

        target_compact = target_lower.replace(" ", "")
        compact_text = "".join(compact_chars)
        compact_index = compact_text.find(target_compact)

        if compact_index != -1 and target_compact:
            start_entry = compact_map[compact_index]
            end_entry = compact_map[compact_index + len(target_compact) - 1] + 1
        else:
            combined_text = "".join(entry["char"] for entry in combined_entries)
            combined_lower = combined_text.lower()
            index = combined_lower.find(target_lower)
            if index == -1:
                return None
            start_entry = index
            end_entry = index + len(target_lower)

        # Extend range to include interior spaces between characters
        while start_entry > 0 and combined_entries[start_entry]["char"] == " ":
            start_entry -= 1
        while end_entry < len(combined_entries) and combined_entries[end_entry - 1]["char"] == " ":
            end_entry += 1

        record_ranges: Dict[str, Dict[str, object]] = {}
        matched_span_order: List[str] = []
        matched_font = None
        matched_fontsize = 0.0

        for idx in range(start_entry, end_entry):
            entry = combined_entries[idx]
            record = entry["record"]
            glyph_idx = int(entry["glyph_index"])
            span_id = str(entry.get("span_id"))
            raw_index = self._normalized_to_raw_index(record, glyph_idx)
            if span_id not in record_ranges:
                record_ranges[span_id] = {
                    "record": record,
                    "start_norm": glyph_idx,
                    "end_norm": glyph_idx,
                    "start_raw": raw_index,
                    "end_raw": raw_index,
                }
                matched_span_order.append(span_id)
            else:
                span_data = record_ranges[span_id]
                span_data["start_norm"] = min(int(span_data["start_norm"]), glyph_idx)
                span_data["end_norm"] = max(int(span_data["end_norm"]), glyph_idx)
                span_data["start_raw"] = min(int(span_data["start_raw"]), raw_index)
                span_data["end_raw"] = max(int(span_data["end_raw"]), raw_index)

            if matched_font is None:
                matched_font = getattr(record, "font", None)
            if not matched_fontsize:
                try:
                    matched_fontsize = float(getattr(record, "font_size", 0.0) or 0.0)
                except (TypeError, ValueError):
                    matched_fontsize = 0.0

        if not record_ranges:
            return None

        union_rect: Optional[fitz.Rect] = None
        matched_paths: List[Dict[str, object]] = []
        total_span_len = 0

        for span_id, span_data in record_ranges.items():
            record = span_data["record"]
            glyph_start_norm = int(span_data["start_norm"])
            glyph_end_norm = int(span_data["end_norm"]) + 1
            rect = self._rect_from_record_slice(record, glyph_start_norm, glyph_end_norm)
            if rect is None:
                continue
            union_rect = rect if union_rect is None else union_rect | rect
            raw_start = int(span_data.get("start_raw", glyph_start_norm))
            raw_end = int(span_data.get("end_raw", glyph_end_norm - 1)) + 1
            matched_paths.append(
                {
                    "block": getattr(record, "block_index", None),
                    "line": getattr(record, "line_index", None),
                    "span": getattr(record, "span_index", None),
                    "char_start": raw_start,
                    "char_end": raw_end,
                    "norm_start": glyph_start_norm,
                    "norm_end": glyph_end_norm,
                    "span_id": span_id,
                }
            )
            total_span_len += glyph_end_norm - glyph_start_norm

        if union_rect is None:
            return None

        context["matched_rect"] = tuple(union_rect)
        context["matched_rect_width"] = float(union_rect.width)
        context["matched_font"] = matched_font
        context["matched_fontsize"] = matched_fontsize or 10.0
        context["matched_span_len"] = total_span_len
        context["matched_text"] = self.strip_zero_width(original_text) or target_lower
        context["matched_origin_x"] = float(union_rect.x0)
        context["matched_origin_y"] = float(union_rect.y0)
        context["matched_end_origin_x"] = float(union_rect.x1)
        context["matched_end_origin_y"] = float(union_rect.y1)
        if matched_paths:
            context["matched_glyph_path"] = matched_paths[0]
            context["matched_glyph_paths"] = matched_paths
        if matched_span_order:
            context["matched_span_ids"] = matched_span_order
            context["span_ids"] = matched_span_order
        context.setdefault("stem_span_ids", span_ids)

        fontsize = float(context.get("matched_fontsize") or 0.0) or 10.0
        return union_rect, fontsize, total_span_len

    def locate_text_span(
        self,
        page: fitz.Page,
        context: Dict[str, object],
        used_rects: Optional[List[fitz.Rect]] = None,
        used_fingerprints: Optional[set[str]] = None,
    ) -> Optional[Tuple[fitz.Rect, float, int]]:
        span_ids = (
            context.get("matched_span_ids")
            or context.get("selection_span_ids")
            or context.get("span_ids")
            or context.get("stem_span_ids")
        )
        direct_span_location = self._locate_using_span_ids(page, context, span_ids)
        if direct_span_location:
            rect_candidate, _, _ = direct_span_location
            if used_rects and self._rects_conflict(rect_candidate, used_rects):
                return None
            return direct_span_location

        original = str(context.get("original") or "").strip()
        if not original:
            return None

        clip_data = (
            context.get("selection_bbox")
            or context.get("stem_bbox")
            or context.get("bbox")
        )
        clip_rect = None
        if clip_data and len(clip_data) == 4:
            try:
                clip_rect = fitz.Rect(*clip_data)
            except Exception:
                clip_rect = None

        selection_rect = None
        selection_bbox = context.get("selection_bbox")
        selection_quads = context.get("selection_quads") or []
        if selection_bbox and len(selection_bbox) == 4:
            try:
                selection_rect = fitz.Rect(*selection_bbox)
            except Exception:
                selection_rect = None
        if selection_rect is None and selection_quads:
            selection_rect = self._rect_from_quads(selection_quads)

        if selection_rect is not None:
            info = self._span_info_from_rect(page, selection_rect, context)
            if info:
                rect, fontsize, span_len = info
                if used_rects and self._rects_conflict(rect, used_rects):
                    return None
                return rect, fontsize, span_len

        padded_rect = None
        if clip_rect is not None:
            padded_rect = fitz.Rect(clip_rect)
            padded_rect.x0 -= 6
            padded_rect.y0 -= 6
            padded_rect.x1 += 6
            padded_rect.y1 += 6

        occurrences = self._find_occurrences(page, original)
        if not occurrences:
            return None

        expected_prefix = str(context.get("prefix") or "")
        expected_suffix = str(context.get("suffix") or "")
        expected_occurrence = context.get("occurrence_index")
        fingerprint_key = context.get("fingerprint_key")

        used_fingerprints = used_fingerprints or set()

        occurrence_in_scope = 0

        for occ in occurrences:
            rect = occ.get("rect")
            if not isinstance(rect, fitz.Rect):
                continue

            if clip_rect is not None:
                if padded_rect and not rect.intersects(padded_rect):
                    continue

            if clip_rect is not None and not rect.intersects(clip_rect):
                continue

            if used_rects and self._rects_conflict(rect, used_rects):
                continue

            if fingerprint_key and fingerprint_key in used_fingerprints:
                continue

            if not self._fingerprint_matches(occ, expected_prefix, expected_suffix):
                occurrence_in_scope += 1
                continue

            context["matched_rect"] = tuple(rect)
            context["matched_occurrence"] = occurrence_in_scope
            context["matched_fontsize"] = occ.get("fontsize")
            context["matched_span_len"] = occ.get("span_len")
            context["matched_text"] = occ.get("text")
            if fingerprint_key:
                context["matched_fingerprint_key"] = fingerprint_key

            fontsize = float(occ.get("fontsize", 10.0))
            span_len = int(occ.get("span_len", len(original)))

            return rect, fontsize, span_len

        return None

    # === Custom Font Replacement Methods ===================================================

    def calculate_courier_font_size(self, replacement_text: str, target_width_pts: float, original_text: str = "") -> float:
        """
        Calculate intelligent Courier font size with smart scaling strategy.

        When replacement is shorter than original: use reasonable font size + spacing
        When replacement is longer than original: scale down to fit
        """
        if not replacement_text:
            return 8.0  # Default size for empty replacements

        # Courier character width ratio (0.6em per character)
        courier_char_width_ratio = 0.6
        replacement_length = len(replacement_text)
        original_length = len(original_text) if original_text else replacement_length

        # Calculate what font size would be needed for perfect fit
        required_font_size = target_width_pts / (replacement_length * courier_char_width_ratio)

        # Smart scaling strategy
        if replacement_length <= original_length:
            # Replacement is shorter or same length - avoid excessive scaling up
            # Use minimum viable font size and rely on spacing to fill the gap
            reasonable_font_size = min(required_font_size, 12.0)  # Cap at 12pt for readability
            return max(6.0, reasonable_font_size)  # Minimum 6pt for readability
        else:
            # Replacement is longer - scale down to fit but maintain readability
            scaled_font_size = required_font_size
            return max(4.0, min(scaled_font_size, 16.0))  # Between 4pt and 16pt

    def calculate_text_width_courier(self, text: str, font_size: float) -> float:
        """
        Calculate visual width of text using Courier font at given size.
        """
        if not text:
            return 0.0

        courier_char_width_ratio = 0.6
        return len(text) * font_size * courier_char_width_ratio

    def split_tj_operator_for_font_replacement(
        self,
        original_tj_array: ArrayObject,
        replace_start_idx: int,
        replace_end_idx: int,
        replacement_text: str,
        original_width_pts: float,
        current_font_name: Optional[str] = "/F1",
        current_font_size: float = 12.0,
    ) -> List[Tuple[List[object], bytes]]:
        """
        Split a TJ operator to allow font change for replacement text.

        Returns a list of PDF operations that replace the original TJ operator.
        """
        operations = []

        # Part 1: Before replacement (keep original font)
        before_array = ArrayObject(original_tj_array[:replace_start_idx])
        if len(before_array) > 0:
            operations.append(([before_array], b'TJ'))

        # Part 2: Replacement text with Courier font
        if replacement_text:
            # Calculate perfect Courier font size
            courier_font_size = self.calculate_courier_font_size(replacement_text, original_width_pts)

            # Switch to Courier
            operations.append(([NameObject('/Courier'), NumberObject(courier_font_size)], b'Tf'))

            # Insert replacement text
            replacement_array = ArrayObject([TextStringObject(replacement_text)])
            operations.append(([replacement_array], b'TJ'))

            # Calculate any needed spacing adjustment for perfect width match
            actual_width = self.calculate_text_width_courier(replacement_text, courier_font_size)
            width_diff = original_width_pts - actual_width

            if abs(width_diff) > 0.1:  # Add spacing if significant difference
                spacing_adjustment = -(width_diff * 1000) / courier_font_size
                spacing_array = ArrayObject([NumberObject(spacing_adjustment)])
                operations.append(([spacing_array], b'TJ'))

        else:
            # Empty replacement - just add spacing to fill the gap
            spacing_adjustment = -(original_width_pts * 1000) / current_font_size
            spacing_array = ArrayObject([NumberObject(spacing_adjustment)])
            operations.append(([spacing_array], b'TJ'))

        # Part 3: Restore original font for remaining text
        after_array = ArrayObject(original_tj_array[replace_end_idx:])
        if len(after_array) > 0:
            # Restore original font
            operations.append(([NameObject(current_font_name), NumberObject(current_font_size)], b'Tf'))
            operations.append(([after_array], b'TJ'))

        return operations

    def handle_text_replacement_edge_cases(
        self,
        replacement_text: str,
        target_width_pts: float,
        max_readable_font_size: float = 4.0,
    ) -> Tuple[str, str]:
        """
        Handle edge cases for text replacement (very long text, empty text, etc.).

        Returns: (processed_replacement_text, strategy_used)
        """
        if not replacement_text:
            return "", "empty_replacement"

        # Calculate minimum required font size
        required_font_size = self.calculate_courier_font_size(replacement_text, target_width_pts)

        if required_font_size >= max_readable_font_size:
            return replacement_text, "normal_replacement"

        # Text is too long for readable font size - need to abbreviate
        courier_char_width_ratio = 0.6
        max_chars = int(target_width_pts / (max_readable_font_size * courier_char_width_ratio))

        if max_chars <= 3:
            # Extremely narrow space - use single character or empty
            return replacement_text[0] if replacement_text else "", "single_char"

        elif max_chars <= len(replacement_text):
            # Abbreviate with ellipsis
            abbreviated = replacement_text[:max_chars-3] + "..."
            return abbreviated, "abbreviated"

        else:
            # Should fit normally (fallback case)
            return replacement_text, "normal_replacement"

    def _rebuild_operations_with_courier_font(
        self,
        operations: List[Tuple[List[object], bytes]],
        segments: List[Dict[str, object]],
        replacements: List[Dict[str, object]],
        run_id: Optional[str] = None,
    ) -> List[Tuple[List[object], bytes]]:
        """
        New rebuild operations method that uses Courier font strategy.

        Instead of rebuilding entire TJ operators, we split them surgically
        and use Courier font for replacement text with perfect width matching.
        """
        segments_by_index = {seg["index"]: seg for seg in segments}
        updated: List[Tuple[List[object], bytes]] = []

        # Group replacements by segment index for processing
        replacements_by_segment = defaultdict(list)
        for replacement in replacements:
            # Find which segment this replacement belongs to
            start_pos = replacement.get("start", 0)
            for seg in segments:
                if seg["start"] <= start_pos < seg["end"]:
                    replacements_by_segment[seg["index"]].append(replacement)
                    break

        for idx, (operands, operator) in enumerate(operations):
            segment = segments_by_index.get(idx)
            segment_replacements = replacements_by_segment.get(idx, [])

            # If no segment or no replacements, keep original operation
            if not segment or not segment_replacements:
                updated.append((operands, operator))
                continue

            # Handle TJ/Tj operators with replacements
            if operator in (b"TJ", b"Tj") and segment_replacements:
                try:
                    split_operations = self._process_tj_replacements(
                        operands, operator, segment, segment_replacements, run_id
                    )
                    updated.extend(split_operations)
                except Exception as exc:
                    # Fallback to original operation if splitting fails
                    self.logger.warning(
                        "TJ splitting failed, using original operation",
                        extra={"run_id": run_id, "error": str(exc)},
                    )
                    updated.append((operands, operator))
            else:
                # Non-text operators or no replacements
                updated.append((operands, operator))

        return updated

    def _coerce_text_operator_operands(
        self,
        operands: List[object],
        operator: bytes,
    ) -> Tuple[ArrayObject, bytes]:
        if operator == b"TJ":
            if operands and isinstance(operands[0], ArrayObject):
                return ArrayObject(list(operands[0])), b"TJ"
            return ArrayObject(), b"TJ"
        if operator == b"Tj":
            literal = operands[0] if operands else TextStringObject("")
            return ArrayObject([literal]), b"Tj"
        return ArrayObject(), operator

    def _decode_text_operand(self, operand: object) -> str:
        if isinstance(operand, TextStringObject):
            return str(operand)
        if isinstance(operand, ByteStringObject):
            try:
                return operand.decode("latin-1")
            except Exception:
                return operand.decode("latin-1", errors="ignore")
        return ""

    def _clone_text_operand(self, template: object, text: str) -> object:
        if isinstance(template, ByteStringObject):
            try:
                data = text.encode("latin-1")
            except UnicodeEncodeError:
                data = text.encode("latin-1", "replace")
            return ByteStringObject(data)
        return TextStringObject(text)

    def _build_tj_entries(self, array: ArrayObject) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        cursor = 0
        for item in array:
            if isinstance(item, (TextStringObject, ByteStringObject)):
                text_value = self._decode_text_operand(item)
                entry = {
                    "kind": "text",
                    "template": item,
                    "text": text_value,
                    "value": 0.0,
                    "adds_space": False,
                    "keep": True,
                    "start": cursor,
                    "end": cursor + len(text_value),
                }
                cursor += len(text_value)
                entries.append(entry)
            elif isinstance(item, NumberObject):
                value = float(item)
                adds_space = value <= self._SPACE_THRESHOLD
                char_length = 1 if adds_space else 0
                entry = {
                    "kind": "kern",
                    "template": item,
                    "text": "",
                    "value": value,
                    "adds_space": adds_space,
                    "keep": True,
                    "start": cursor,
                    "end": cursor + char_length,
                }
                cursor += char_length
                entries.append(entry)
            else:
                entries.append(
                    {
                        "kind": "other",
                        "template": item,
                        "text": "",
                        "value": None,
                        "adds_space": False,
                        "keep": True,
                        "start": cursor,
                        "end": cursor,
                    }
                )
        return entries

    def _recalculate_tj_entries(self, entries: List[Dict[str, object]]) -> int:
        cursor = 0
        for entry in entries:
            if not entry.get("keep", True):
                entry["start"] = cursor
                entry["end"] = cursor
                continue
            if entry["kind"] == "text":
                length = len(entry.get("text", ""))
            elif entry["kind"] == "kern" and entry.get("adds_space"):
                length = 1
            else:
                length = 0
            entry["start"] = cursor
            entry["end"] = cursor + length
            cursor = entry["end"]
        return cursor

    def _build_tj_char_index(
        self, entries: List[Dict[str, object]]
    ) -> Tuple[List[Dict[str, int]], Dict[int, List[int]]]:
        char_map: List[Dict[str, int]] = []
        chars_by_entry: Dict[int, List[int]] = defaultdict(list)
        for entry_index, entry in enumerate(entries):
            if not entry.get("keep", True):
                continue
            if entry["kind"] == "text":
                text_value = entry.get("text", "")
                for offset in range(len(text_value)):
                    position = len(char_map)
                    char_map.append({"entry": entry_index, "kind": "text", "offset": offset})
                    chars_by_entry[entry_index].append(position)
            elif entry["kind"] == "kern" and entry.get("adds_space"):
                position = len(char_map)
                char_map.append({"entry": entry_index, "kind": "kern_space", "offset": 0})
                chars_by_entry[entry_index].append(position)
        return char_map, chars_by_entry

    def _find_entry_index_between(
        self,
        char_map: List[Dict[str, int]],
        start: int,
        end: int,
        forward: bool = True,
    ) -> Optional[int]:
        if not char_map:
            return None
        lower = max(0, min(start, len(char_map)))
        upper = max(0, min(end, len(char_map)))
        if forward:
            indices = range(lower, upper)
        else:
            indices = range(upper - 1, lower - 1, -1)
        for idx in indices:
            token = char_map[idx]
            if token["kind"] == "text":
                return token["entry"]
        return None

    def _find_entry_index_before(
        self,
        entries: List[Dict[str, object]],
        char_map: List[Dict[str, int]],
        position: int,
    ) -> Optional[int]:
        if char_map:
            idx = min(position, len(char_map)) - 1
            while idx >= 0:
                token = char_map[idx]
                if token["kind"] == "text":
                    return token["entry"]
                idx -= 1
        for entry_index in range(len(entries) - 1, -1, -1):
            entry = entries[entry_index]
            if entry.get("keep", True) and entry["kind"] == "text":
                return entry_index
        return None

    def _find_entry_index_after(
        self,
        entries: List[Dict[str, object]],
        char_map: List[Dict[str, int]],
        position: int,
    ) -> Optional[int]:
        if char_map:
            idx = max(0, min(position, len(char_map)))
            while idx < len(char_map):
                token = char_map[idx]
                if token["kind"] == "text":
                    return token["entry"]
                idx += 1
        for entry_index, entry in enumerate(entries):
            if entry.get("keep", True) and entry["kind"] == "text":
                return entry_index
        return None

    def _get_default_text_template(self, entries: List[Dict[str, object]]) -> object:
        for entry in entries:
            if entry["kind"] == "text":
                return entry["template"]
        return TextStringObject("")

    def _make_text_entry(self, template: object, text: str) -> Dict[str, object]:
        return {
            "kind": "text",
            "template": template,
            "text": text,
            "value": 0.0,
            "adds_space": False,
            "keep": True,
            "start": 0,
            "end": 0,
        }

    def _apply_tj_insertion(
        self,
        entries: List[Dict[str, object]],
        position: int,
        replacement_text: str,
        char_map: List[Dict[str, int]],
        chars_by_entry: Dict[int, List[int]],
    ) -> None:
        if not replacement_text:
            return
        entry_index = self._find_entry_index_between(char_map, position, position + 1)
        if entry_index is None:
            entry_index = self._find_entry_index_after(entries, char_map, position)
        if entry_index is None:
            entry_index = self._find_entry_index_before(entries, char_map, position)
        if entry_index is None:
            template = self._get_default_text_template(entries)
            entries.append(self._make_text_entry(template, replacement_text))
            self._recalculate_tj_entries(entries)
            return

        entry = entries[entry_index]
        text_value = entry.get("text", "")
        positions = chars_by_entry.get(entry_index, [])
        if positions:
            insert_offset = bisect_left(positions, min(position, len(char_map)))
        else:
            insert_offset = len(text_value) if position >= entry.get("end", 0) else 0
        entry["text"] = text_value[:insert_offset] + replacement_text + text_value[insert_offset:]
        entry["keep"] = True
        self._recalculate_tj_entries(entries)

    def _apply_tj_substitution(
        self,
        entries: List[Dict[str, object]],
        local_start: int,
        local_end: int,
        replacement_text: str,
    ) -> None:
        start_boundary = max(local_start, 0)
        end_boundary = max(local_end, start_boundary)

        initial_length = self._recalculate_tj_entries(entries)
        initial_positions = [entry.get("start", 0) for entry in entries]

        total_length = initial_length
        clip_start = min(max(local_start, 0), total_length)
        clip_end = min(max(local_end, clip_start), total_length)

        char_map, chars_by_entry = self._build_tj_char_index(entries)

        if clip_start == clip_end:
            if replacement_text:
                self._apply_tj_insertion(entries, clip_start, replacement_text, char_map, chars_by_entry)
            return

        first_text_index = self._find_entry_index_between(char_map, clip_start, clip_end, forward=True)
        if first_text_index is None:
            first_text_index = self._find_entry_index_before(entries, char_map, clip_start)
        if first_text_index is None:
            first_text_index = self._find_entry_index_after(entries, char_map, clip_end)

        if first_text_index is None:
            template = self._get_default_text_template(entries)
            entries.append(self._make_text_entry(template, replacement_text))
            self._recalculate_tj_entries(entries)
            return

        last_text_index = self._find_entry_index_between(char_map, clip_start, clip_end, forward=False)
        if last_text_index is None:
            last_text_index = first_text_index
        if last_text_index < first_text_index:
            last_text_index = first_text_index

        first_entry = entries[first_text_index]
        first_positions = chars_by_entry.get(first_text_index, [])
        prefix_chars = bisect_left(first_positions, clip_start) if first_positions else 0
        prefix_text = first_entry.get("text", "")[:prefix_chars]

        if first_text_index == last_text_index:
            total_chars = len(first_positions)
            suffix_chars = 0
            if total_chars:
                suffix_chars = total_chars - bisect_right(first_positions, clip_end - 1)
            suffix_chars = max(0, min(suffix_chars, len(first_entry.get("text", ""))))
            suffix_start = len(first_entry.get("text", "")) - suffix_chars
            suffix_text = first_entry.get("text", "")[suffix_start:]
            first_entry["text"] = prefix_text + replacement_text + suffix_text
            first_entry["keep"] = True
        else:
            first_entry["text"] = prefix_text + replacement_text
            first_entry["keep"] = True

            last_entry = entries[last_text_index]
            last_positions = chars_by_entry.get(last_text_index, [])
            suffix_chars = 0
            if last_positions:
                suffix_chars = len(last_positions) - bisect_right(last_positions, clip_end - 1)
            suffix_chars = max(0, min(suffix_chars, len(last_entry.get("text", ""))))
            if suffix_chars:
                last_entry["text"] = last_entry.get("text", "")[-suffix_chars:]
                last_entry["keep"] = True
            else:
                last_entry["text"] = ""
                last_entry["keep"] = False

            for index in range(first_text_index + 1, last_text_index):
                middle_entry = entries[index]
                if middle_entry["kind"] == "text":
                    middle_entry["text"] = ""
                    middle_entry["keep"] = False

        for entry in entries:
            if entry["kind"] == "text" and not entry.get("text"):
                entry["keep"] = False

        for index, entry in enumerate(entries):
            if entry["kind"] == "kern" and entry.get("keep", True):
                position = initial_positions[index]
                if start_boundary <= position < end_boundary:
                    entry["keep"] = False

        self._recalculate_tj_entries(entries)

    def _apply_tj_edit(
        self,
        entries: List[Dict[str, object]],
        local_start: int,
        local_end: int,
        replacement_text: str,
    ) -> None:
        replacement_text = str(replacement_text or "")
        local_start = max(local_start, 0)
        local_end = max(local_end, local_start)
        if local_start == local_end:
            total_length = self._recalculate_tj_entries(entries)
            char_map, chars_by_entry = self._build_tj_char_index(entries)
            self._apply_tj_insertion(entries, min(local_start, total_length), replacement_text, char_map, chars_by_entry)
            return

        self._apply_tj_substitution(entries, local_start, local_end, replacement_text)

    def _entries_to_tj_array(self, entries: List[Dict[str, object]]) -> ArrayObject:
        array = ArrayObject()
        for entry in entries:
            if not entry.get("keep", True):
                continue
            if entry["kind"] == "text":
                literal = self._clone_text_operand(entry["template"], entry.get("text", ""))
                array.append(literal)
            elif entry["kind"] == "kern":
                array.append(NumberObject(float(entry.get("value", 0.0))))
            else:
                array.append(entry["template"])
        return array

    def _entries_to_segment_state(
        self, entries: List[Dict[str, object]]
    ) -> Tuple[str, Dict[int, float]]:
        text_parts: List[str] = []
        cursor = 0
        kern_map: Dict[int, float] = {}
        for entry in entries:
            if not entry.get("keep", True):
                continue
            if entry["kind"] == "text":
                text_value = entry.get("text", "")
                text_parts.append(text_value)
                cursor += len(text_value)
            elif entry["kind"] == "kern":
                value = float(entry.get("value", 0.0))
                if entry.get("adds_space"):
                    text_parts.append(" ")
                    cursor += 1
                if abs(value) >= 1e-6:
                    kern_map[cursor] = float(kern_map.get(cursor, 0.0) + value)
        return "".join(text_parts), kern_map

    def _process_tj_replacements(
        self,
        operands: List[object],
        operator: bytes,
        segment: Dict[str, object],
        replacements: List[Dict[str, object]],
        run_id: Optional[str] = None,
    ) -> List[Tuple[List[object], bytes]]:
        array_operands, operator_type = self._coerce_text_operator_operands(operands, operator)
        entries = self._build_tj_entries(array_operands)

        self._save_debug_stream(run_id, "before_reconstruction", array_operands, operator_type)

        if not replacements:
            return [([array_operands], operator_type)]

        segment_start = int(segment.get("start", 0))
        replacements_sorted = sorted(replacements, key=lambda item: int(item.get("start", 0)))

        baseline_text = "".join(
            entry.get("text", "")
            for entry in entries
            if entry.get("keep", True) and entry.get("kind") == "text"
        )
        reserved_ranges: List[Tuple[int, int]] = []

        for replacement in reversed(replacements_sorted):
            start = int(replacement.get("start", 0)) - segment_start
            end = int(replacement.get("end", 0)) - segment_start
            replacement_text = str(replacement.get("replacement") or "")
            ctx = replacement.get("context", {}) or {}
            original_subtext = str(ctx.get("matched_text") or ctx.get("original") or "")

            if end <= start:
                start = max(start, 0)
                end = max(end, start)

            if end <= start and original_subtext:
                candidate_len = len(original_subtext)
                search_idx = max(0, min(len(baseline_text), start))
                fallback_idx = baseline_text.find(original_subtext, search_idx)
                if fallback_idx == -1:
                    fallback_idx = baseline_text.find(original_subtext)
                while fallback_idx != -1:
                    candidate = (fallback_idx, fallback_idx + candidate_len)
                    if not any(
                        candidate[0] < taken_end and candidate[1] > taken_start
                        for taken_start, taken_end in reserved_ranges
                    ):
                        start, end = candidate
                        break
                    fallback_idx = baseline_text.find(original_subtext, fallback_idx + 1)

            if end <= start:
                if run_id:
                    self.logger.warning(
                        "unable to resolve replacement bounds for segment",
                        extra={
                            "run_id": run_id,
                            "start_offset": start,
                            "end_offset": end,
                            "replacement": replacement_text,
                            "original_subtext": original_subtext,
                        },
                    )
                replacement["applied"] = False
                continue

            prev_text, _ = self._entries_to_segment_state(entries)
            self._apply_tj_edit(entries, start, end, replacement_text)
            updated_text, _ = self._entries_to_segment_state(entries)

            if updated_text == prev_text:
                replacement["applied"] = False
                if run_id:
                    self.logger.warning(
                        "replacement left segment unchanged",
                        extra={
                            "run_id": run_id,
                            "start_offset": start,
                            "end_offset": end,
                            "replacement": replacement_text,
                            "original_subtext": original_subtext,
                        },
                    )
                continue

            replacement["applied"] = True
            span_length = len(original_subtext) or len(replacement_text)
            reserved_ranges.append((start, start + span_length))
            baseline_text = updated_text

        if not any(entry.get("keep", True) and entry["kind"] == "text" for entry in entries):
            template = self._get_default_text_template(entries)
            entries.append(self._make_text_entry(template, ""))
            self._recalculate_tj_entries(entries)

        new_array = self._entries_to_tj_array(entries)
        text_value, kern_map = self._entries_to_segment_state(entries)

        previous_text = segment.get("text", "") or ""
        previous_kern = dict(segment.get("kern_map") or {})

        segment["text"] = text_value
        segment["kern_map"] = kern_map
        segment["modified"] = bool(segment.get("modified")) or text_value != previous_text or kern_map != previous_kern
        segment["end"] = int(segment.get("start", 0)) + len(text_value)

        original_font = None
        original_size = 12.0
        font_ctx = segment.get("font_context") or {}
        if isinstance(font_ctx, dict):
            original_font = font_ctx.get("font")
            try:
                original_size = float(font_ctx.get("fontsize") or original_size)
            except (TypeError, ValueError):
                original_size = 12.0
        if not original_font:
            original_font = "/F1"

        text_value = segment.get("text", "") or ""
        operations: List[Tuple[List[object], bytes]] = []
        cursor = 0

        for replacement in replacements_sorted:
            if not replacement.get("applied"):
                continue

            ctx = replacement.get("context", {}) or {}
            replacement_text = str(replacement.get("replacement") or "")
            original_subtext = str(ctx.get("matched_text") or ctx.get("original") or "")

            search_start = max(cursor, 0)
            insertion_index = text_value.find(replacement_text, search_start)
            if insertion_index == -1:
                insertion_index = text_value.find(replacement_text)
            if insertion_index == -1:
                insertion_index = search_start

            if insertion_index > cursor:
                before_text = text_value[cursor:insertion_index]
                if before_text:
                    before_array = ArrayObject([TextStringObject(before_text)])
                    operations.append(([before_array], b"TJ"))

            target_width = ctx.get("matched_rect_width") or ctx.get("available_width") or ctx.get("matched_width")
            try:
                target_width = float(target_width) if target_width is not None else None
            except (TypeError, ValueError):
                target_width = None
            if not target_width:
                reference_text = original_subtext or replacement_text
                target_width = float(len(reference_text)) * (original_size or 12.0)

            courier_font_size = self.calculate_courier_font_size(
                replacement_text,
                float(target_width),
                original_subtext,
            )

            operations.append(([NameObject('/Courier'), NumberObject(courier_font_size)], b'Tf'))
            replacement_array = ArrayObject([TextStringObject(replacement_text)])
            operations.append(([replacement_array], b"TJ"))
            operations.append(([NameObject(original_font), NumberObject(original_size)], b'Tf'))

            cursor = insertion_index + len(replacement_text)

        if cursor < len(text_value):
            after_text = text_value[cursor:]
            if after_text:
                after_array = ArrayObject([TextStringObject(after_text)])
                operations.append(([after_array], b"TJ"))

        if not operations:
            operations = [([new_array], b"TJ" if operator_type == b"TJ" else b"Tj")]

        self._save_debug_stream(run_id, "after_reconstruction", operations)

        return operations

    def _save_debug_stream(
        self,
        run_id: Optional[str],
        stage: str,
        data: object,
        operator: bytes = b'TJ'
    ) -> None:
        """
        Save debug information about stream reconstruction to artifacts folder.
        """
        if not run_id:
            return

        try:
            from ....utils.storage_paths import method_stage_artifact_path
            from pathlib import Path
            import json

            debug_dir = method_stage_artifact_path(run_id, "stream_rewrite-overlay", "debug")
            debug_dir.mkdir(parents=True, exist_ok=True)

            if isinstance(data, list):
                # Multiple operations
                debug_content = {
                    'stage': stage,
                    'operations': []
                }
                for i, (operands, op) in enumerate(data):
                    debug_content['operations'].append({
                        'index': i,
                        'operator': op.decode('latin-1'),
                        'operands': [str(operand) for operand in operands]
                    })
            else:
                # Single TJ array
                debug_content = {
                    'stage': stage,
                    'operator': operator.decode('latin-1'),
                    'tj_elements': [str(elem) for elem in data] if hasattr(data, '__iter__') else [str(data)]
                }

            debug_file = debug_dir / f"{stage}.json"
            with open(debug_file, 'w') as f:
                json.dump(debug_content, f, indent=2)

        except Exception as e:
            self.logger.warning(f"Failed to save debug stream: {e}", extra={"run_id": run_id})

    def _save_enhanced_debug(
        self,
        run_id: Optional[str],
        stage: str,
        original_pdf_path: Path,
        page_index: int = 0,
        operations_before: List[Tuple[List[object], bytes]] = None,
        operations_after: List[Tuple[List[object], bytes]] = None,
        font_context: Dict[str, object] = None
    ) -> None:
        """
        Save comprehensive debug information including full page hierarchy and text matrix positions.
        """
        if not run_id:
            return

        try:
            from ....utils.storage_paths import method_stage_artifact_path
            import fitz
            from PyPDF2 import PdfReader
            from PyPDF2.generic import ContentStream
            import json

            debug_dir = method_stage_artifact_path(run_id, "stream_rewrite-overlay", "debug")
            debug_dir.mkdir(parents=True, exist_ok=True)

            # Read original PDF for analysis
            pdf_bytes = original_pdf_path.read_bytes()
            reader = PdfReader(io.BytesIO(pdf_bytes))
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            page = reader.pages[page_index] if page_index < len(reader.pages) else None
            fitz_page = doc[page_index] if page_index < len(doc) else None

            debug_data = {
                "stage": stage,
                "run_id": run_id,
                "page_index": page_index,
                "font_context": font_context or {},
                "text_matrix_analysis": {},
                "full_page_hierarchy": {},
                "operations_comparison": {}
            }

            # Extract full page hierarchy using PyMuPDF
            if fitz_page:
                text_dict = fitz_page.get_text('dict')
                debug_data["full_page_hierarchy"] = {
                    "page_width": fitz_page.rect.width,
                    "page_height": fitz_page.rect.height,
                    "blocks": []
                }

                for block_num, block in enumerate(text_dict.get('blocks', [])):
                    if 'lines' in block:
                        block_info = {
                            "block_number": block_num,
                            "bbox": block.get('bbox', []),
                            "lines": []
                        }

                        for line_num, line in enumerate(block['lines']):
                            line_info = {
                                "line_number": line_num,
                                "bbox": line.get('bbox', []),
                                "spans": []
                            }

                            for span_num, span in enumerate(line.get('spans', [])):
                                span_info = {
                                    "span_number": span_num,
                                    "text": span.get('text', ''),
                                    "font": span.get('font', ''),
                                    "size": span.get('size', 0),
                                    "flags": span.get('flags', 0),
                                    "color": span.get('color', 0),
                                    "bbox": span.get('bbox', []),
                                    "matrix": span.get('matrix', [])
                                }
                                line_info["spans"].append(span_info)

                            block_info["lines"].append(line_info)
                        debug_data["full_page_hierarchy"]["blocks"].append(block_info)

            # Extract text matrix positions using PyPDF2 content stream
            if page:
                content_stream = ContentStream(page.get_contents(), reader)
                debug_data["text_matrix_analysis"] = self._analyze_text_matrix_positions(content_stream)

            # Compare operations before and after
            if operations_before or operations_after:
                debug_data["operations_comparison"] = {
                    "before": self._format_operations_for_debug(operations_before) if operations_before else [],
                    "after": self._format_operations_for_debug(operations_after) if operations_after else []
                }

            # Save to file
            debug_file = debug_dir / f"{stage}_enhanced.json"
            with open(debug_file, 'w') as f:
                json.dump(debug_data, f, indent=2)

            doc.close()

        except Exception as exc:
            self.logger.warning(
                f"Failed to save enhanced debug: {exc}",
                extra={"run_id": run_id, "stage": stage}
            )

    def _analyze_text_matrix_positions(self, content_stream: ContentStream) -> Dict[str, object]:
        """
        Analyze text matrix positions from PDF content stream.
        """
        text_positions = []
        current_matrix = [1, 0, 0, 1, 0, 0]  # Default text matrix

        try:
            for operands, operator in content_stream.operations:
                if operator == b'Tm':
                    # Text matrix operator
                    if len(operands) >= 6:
                        current_matrix = [float(op) for op in operands]
                        text_positions.append({
                            "operator": "Tm",
                            "matrix": current_matrix.copy(),
                            "position": [current_matrix[4], current_matrix[5]]
                        })
                elif operator == b'Td':
                    # Text positioning operator
                    if len(operands) >= 2:
                        dx, dy = float(operands[0]), float(operands[1])
                        current_matrix[4] += dx
                        current_matrix[5] += dy
                        text_positions.append({
                            "operator": "Td",
                            "offset": [dx, dy],
                            "matrix": current_matrix.copy(),
                            "position": [current_matrix[4], current_matrix[5]]
                        })
                elif operator in [b'TJ', b'Tj']:
                    # Text showing operators
                    text_positions.append({
                        "operator": operator.decode('ascii', errors='ignore'),
                        "operands": [str(op) for op in operands],
                        "matrix": current_matrix.copy(),
                        "position": [current_matrix[4], current_matrix[5]]
                    })

        except Exception as exc:
            self.logger.warning(f"Error analyzing text matrix: {exc}")

        return {
            "total_positions": len(text_positions),
            "positions": text_positions
        }

    def _format_operations_for_debug(self, operations: List[Tuple[List[object], bytes]]) -> List[Dict[str, object]]:
        """
        Format operations list for debug output.
        """
        formatted = []
        for i, (operands, operator) in enumerate(operations):
            formatted.append({
                "index": i,
                "operator": operator.decode('ascii', errors='ignore'),
                "operands": [str(op) for op in operands]
            })
        return formatted
