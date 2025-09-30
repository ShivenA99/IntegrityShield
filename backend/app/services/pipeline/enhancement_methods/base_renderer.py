from __future__ import annotations

from abc import ABC
import difflib
from collections import OrderedDict, defaultdict
import copy
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Tuple, Optional

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


class BaseRenderer:
    _ZERO_WIDTH_MARKERS = (
        "\u200B",  # zero-width space
        "\u200C",  # zero-width non-joiner
        "\u200D",  # zero-width joiner
        "\u2060",  # word joiner
        "\u2061",  # function application
        "\u2062",  # invisible times
        "\u2063",  # invisible separator
    )

    def __init__(self) -> None:
        self.structured_manager = StructuredDataManager()
        self.logger = get_logger(self.__class__.__name__)

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

        payload: Dict[str, object] = {
            "q_number": q_label,
            "stem_text": stem_text,
            "page": page_idx,
            "stem_bbox": bbox,
            "question_type": question_type,
            "options": options,
            "substring_mappings": substring_mappings,
        }

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

            if selection_bbox:
                context["bbox"] = tuple(selection_bbox)

            contexts.append(context)

        return contexts

    def _fingerprint_matches(
        self,
        occurrence: Dict[str, object],
        expected_prefix: str,
        expected_suffix: str,
    ) -> bool:
        actual_prefix = self.strip_zero_width(str(occurrence.get("prefix") or ""))
        actual_suffix = self.strip_zero_width(str(occurrence.get("suffix") or ""))

        expected_prefix_clean = self.strip_zero_width(expected_prefix)
        expected_suffix_clean = self.strip_zero_width(expected_suffix)

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
            glyph_path = ctx.get("matched_glyph_path") or {}
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

            # Clamp indices to valid range
            char_start = max(0, min(int(char_start), char_count - 1))
            char_end = max(0, min(int(char_end), char_count))
            if char_end <= char_start:
                continue

            raw_start = positions[char_start]
            raw_end = positions[char_end]
            stream_origin = None
            if origins and char_start < len(origins):
                stream_origin = origins[char_start]

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

            ctx["stream_range"] = (mapped_start, mapped_end)
            ctx["stream_text"] = combined_text[mapped_start:mapped_end]
            if stream_origin is not None:
                ctx["stream_start_origin"] = float(stream_origin)
            if span_data.get("font"):
                ctx.setdefault("matched_font", span_data.get("font"))
            if span_data.get("fontsize"):
                try:
                    ctx.setdefault("matched_fontsize", float(span_data.get("fontsize")))
                except (TypeError, ValueError):
                    pass

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
                start_candidate = max(0, int(stream_range[0]))
                end_candidate = max(start_candidate, int(stream_range[1]))
                end_candidate = min(end_candidate, len(combined_text))
                if end_candidate > start_candidate and not range_conflicts((start_candidate, end_candidate)):
                    span = (start_candidate, end_candidate)
                    ctx["matched_text"] = ctx.get("stream_text") or combined_text[start_candidate:end_candidate]

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
            used_ranges.append((start, end))
            if fingerprint_key:
                used_fingerprints.add(fingerprint_key)
                local_fingerprints.add(fingerprint_key)

            if end > start:
                ctx["matched_text"] = combined_text[start:end]

            available_width = ctx.get("available_width")
            if not available_width and ctx.get("matched_rect"):
                try:
                    available_width = fitz.Rect(*ctx.get("matched_rect")).width
                except Exception:
                    available_width = None

            font_name = ctx.get("matched_font")
            try:
                font_size = float(ctx.get("matched_fontsize") or 0.0)
            except (TypeError, ValueError):
                font_size = 0.0

            original_text = ctx.get("matched_text") or combined_text[start:end]
            original_width = ctx.get("matched_rect_width")
            if font_name and font_size > 0 and original_text:
                try:
                    original_width = doc_page.get_text_length(original_text, fontname=font_name, fontsize=font_size)
                except Exception:
                    pass

            if available_width is None and original_width is not None:
                available_width = float(original_width)

            replacement_text_str = str(replacement_text)
            replacement_width = 0.0
            glyph_widths: List[float] = []
            if font_name and font_size > 0 and replacement_text_str:
                for ch in replacement_text_str:
                    try:
                        glyph_width = doc_page.get_text_length(ch, fontname=font_name, fontsize=font_size)
                    except Exception:
                        glyph_width = 0.0
                    glyph_widths.append(glyph_width)
                replacement_width = sum(glyph_widths)
            else:
                replacement_width = float(len(replacement_text_str))

            ctx["matched_width"] = float(original_width or 0.0)
            ctx["replacement_width"] = float(replacement_width)

            matched_origin = ctx.get("matched_origin_x")
            stream_origin = ctx.get("stream_start_origin")
            leading_adjust_ts = 0.0
            if font_size > 0 and matched_origin is not None and stream_origin is not None:
                try:
                    delta_left = float(matched_origin) - float(stream_origin)
                    if abs(delta_left) > 1e-3:
                        leading_adjust_ts = -delta_left * 1000.0 / font_size
                except Exception:
                    leading_adjust_ts = 0.0

            target_width = float(original_width or replacement_width)
            delta_width_pt = float(replacement_width) - float(target_width)

            gap_adjust_ts: List[float] = []
            trailing_adjust_ts = 0.0
            char_count = len(replacement_text_str)
            delta_ts_total = 0.0
            if font_size > 0:
                delta_ts_total = (float(replacement_width) - float(target_width)) * 1000.0 / font_size
                trailing_adjust_ts = delta_ts_total

            ctx["leading_adjust_ts"] = leading_adjust_ts
            ctx["gap_adjust_ts"] = gap_adjust_ts
            ctx["trailing_adjust_ts"] = trailing_adjust_ts

            stream_value = float(stream_origin) if stream_origin is not None else float(matched_origin or 0.0)
            matched_value = float(matched_origin) if matched_origin is not None else stream_value
            ctx["rewrite_left_overflow"] = max(0.0, matched_value - stream_value)
            ctx["rewrite_right_overflow"] = max(0.0, float(replacement_width) - float(target_width))

            replacements.append(
                {
                    "start": start,
                    "end": end,
                    "replacement": replacement_text,
                    "context": ctx,
                    "fingerprint_key": fingerprint_key,
                    "applied": False,
                    "scale": 1.0,
                    "kerning_plan": {
                        "leading_adjust_ts": leading_adjust_ts,
                        "gap_adjust_ts": gap_adjust_ts,
                        "trailing_adjust_ts": trailing_adjust_ts,
                    },
                    "replacement_width": replacement_width,
                }
            )

            if font_name and font_size > 0:
                try:
                    self.logger.debug(
                        "kerning plan for replacement",
                        extra={
                            "run_id": run_id,
                            "page": page_index,
                            "q_number": ctx.get("q_number"),
                            "original": ctx.get("original"),
                            "replacement": replacement_text_str,
                            "original_width": float(target_width),
                            "replacement_width": float(replacement_width),
                            "leading_ts": leading_adjust_ts,
                            "trailing_ts": trailing_adjust_ts,
                            "gap_count": len(gap_adjust_ts),
                        },
                    )
                except Exception:
                    pass

        return replacements

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

            actual_prefix = self.strip_zero_width(
                combined_text[max(0, idx - len(expected_prefix)) : idx]
            )
            actual_suffix = self.strip_zero_width(
                combined_text[end : end + len(expected_suffix)]
            )

            prefix_ok = True
            if expected_prefix:
                compare_len = min(len(actual_prefix), len(expected_prefix))
                prefix_ok = actual_prefix[-compare_len:] == expected_prefix[-compare_len:]

            suffix_ok = True
            if expected_suffix:
                compare_len = min(len(actual_suffix), len(expected_suffix))
                suffix_ok = actual_suffix[:compare_len] == expected_suffix[:compare_len]

            if prefix_ok and suffix_ok:
                if occurrence_expected is None or occurrence_counter == occurrence_expected:
                    return idx, end
                occurrence_counter += 1
            else:
                search_start = idx + 1
                continue

            search_start = idx + 1

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
        edits_by_segment: Dict[int, List[Dict[str, object]]] = defaultdict(list)
        modified = False

        for replacement in replacements:
            start = int(replacement.get("start", 0))
            end = int(replacement.get("end", 0))
            insert_text = str(replacement.get("replacement") or "")
            scale_value = float(replacement.get("scale", 1.0))
            kerning_plan = replacement.get("kerning_plan") or {}

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

            plan_has_adjustments = False
            if kerning_plan:
                lead = abs(float(kerning_plan.get("leading_adjust_ts", 0.0)))
                trail = abs(float(kerning_plan.get("trailing_adjust_ts", 0.0)))
                plan_has_adjustments = (lead >= 1e-3) or (trail >= 1e-3)

            inserted = False
            for idx, seg in enumerate(covering_segments):
                seg_start = seg["start"]
                seg_end = seg["end"]
                local_start = max(start, seg_start) - seg_start
                local_end = min(end, seg_end) - seg_start
                if local_end < local_start:
                    continue

                text_fragment = insert_text if not inserted else ""
                plan = {}
                if idx == 0 and kerning_plan:
                    plan = {
                        "leading_adjust_ts": kerning_plan.get("leading_adjust_ts", 0.0),
                        "trailing_adjust_ts": kerning_plan.get("trailing_adjust_ts", 0.0),
                    }
                edits_by_segment[id(seg)].append(
                    {
                        "start": local_start,
                        "end": local_end,
                        "text": text_fragment,
                        "kerning_plan": plan,
                        "insert_len": len(text_fragment),
                    }
                )
                if scale_value < seg.get("scale", 1.0):
                    seg["scale"] = scale_value
                inserted = True

            if scale_value < 0.995 or plan_has_adjustments:
                modified = True

            replacement["applied"] = True

            # Log each replacement for debugging
            from app.services.developer.live_logging_service import live_logging_service
            mapping_id = replacement.get("context", {}).get("mapping_id", "unknown")
            original = replacement.get("context", {}).get("original", "")
            repl_text = replacement.get("context", {}).get("replacement", "")
            q_num = replacement.get("context", {}).get("question_number", "")
            if run_id:
                live_logging_service.emit(
                    run_id,
                    "pdf_creation",
                    "INFO",
                    f"✓ Replacement applied: Q{q_num} '{original}' → '{repl_text}' (mapping_id: {mapping_id})",
                    component="stream_rewrite"
                )

        for seg_id, edits in edits_by_segment.items():
            segment = segment_map.get(seg_id)
            if not segment:
                continue

            original_text = segment.get("text", "") or ""
            original_kerns = dict(segment.get("kern_map") or {})
            text = original_text
            kern_map = dict(original_kerns)

            for edit in sorted(edits, key=lambda item: item.get("start", 0), reverse=True):
                local_start = max(int(edit.get("start", 0)), 0)
                local_end = max(local_start, int(edit.get("end", 0)))
                insert_fragment = str(edit.get("text") or "")
                removed_len = local_end - local_start
                shift = len(insert_fragment) - removed_len

                text = text[:local_start] + insert_fragment + text[local_end:]

                if kern_map:
                    updated_map: Dict[int, float] = {}
                    for pos, value in kern_map.items():
                        if local_start < pos < local_end:
                            continue
                        if pos >= local_end:
                            new_pos = pos + shift
                        else:
                            new_pos = pos
                        updated_map[new_pos] = float(updated_map.get(new_pos, 0.0) + value)
                    kern_map = updated_map

                plan = edit.get("kerning_plan") or {}
                leading_ts = float(plan.get("leading_adjust_ts", 0.0))
                trailing_ts = float(plan.get("trailing_adjust_ts", 0.0))
                insert_len = int(edit.get("insert_len", len(insert_fragment)))

                if abs(leading_ts) >= 1e-3:
                    kern_map[local_start] = float(kern_map.get(local_start, 0.0) + leading_ts)

                if abs(trailing_ts) >= 1e-3 and insert_len >= 0:
                    insert_pos = local_start + insert_len
                    kern_map[insert_pos] = float(kern_map.get(insert_pos, 0.0) + trailing_ts)

            if text != original_text or kern_map != original_kerns:
                segment["text"] = text
                segment["kern_map"] = kern_map
                segment["modified"] = True
                segment["end"] = segment.get("start", 0) + len(text)
                modified = True

        return modified

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
    ) -> Tuple[bytes, Dict[str, int]]:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        contexts_by_page = self._group_contexts_by_page(mapping_context)
        used_fingerprints: set[str] = set()

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
                replacements_applied += sum(1 for item in replacements if item.get("applied"))

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

    def locate_text_span(
        self,
        page: fitz.Page,
        context: Dict[str, object],
        used_rects: Optional[List[fitz.Rect]] = None,
        used_fingerprints: Optional[set[str]] = None,
    ) -> Optional[Tuple[fitz.Rect, float, int]]:
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

            if expected_occurrence is not None and occurrence_in_scope != expected_occurrence:
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

    def _process_tj_replacements(
        self,
        operands: List[object],
        operator: bytes,
        segment: Dict[str, object],
        replacements: List[Dict[str, object]],
        run_id: Optional[str] = None,
    ) -> List[Tuple[List[object], bytes]]:
        """
        Process replacements within a TJ/Tj operator using PRECISION WIDTH MATCHING.

        Key principle: Replace text while preserving exact text matrix positioning.
        """
        if operator == b"TJ":
            tj_array = operands[0] if operands else ArrayObject()
        else:  # Tj
            tj_array = ArrayObject([operands[0]]) if operands else ArrayObject()

        # Save original stream for debugging
        self._save_debug_stream(run_id, "before_reconstruction", tj_array, operator)

        # Extract replacement context with width information and font context
        replacement_contexts = {}
        for replacement in replacements:
            context = replacement.get("context", {})
            original_text = context.get("original", "")
            replacement_text = str(replacement.get("replacement", ""))

            if original_text:
                # Include segment font context for proper font restoration
                enhanced_context = context.copy()
                enhanced_context['segment_font_context'] = segment.get('font_context', {})

                replacement_contexts[original_text] = {
                    'replacement': replacement_text,
                    'original_width': context.get("matched_width", 0.0),
                    'font_size': context.get("matched_fontsize", 12.0),
                    'context': enhanced_context
                }

        if not replacement_contexts:
            return [([tj_array], operator)]

        # Find the first replacement to process
        target_element_idx = None
        target_original = None
        target_info = None

        for i, element in enumerate(tj_array):
            if isinstance(element, (TextStringObject, ByteStringObject)):
                element_text = str(element)
                for original_text, info in replacement_contexts.items():
                    if original_text in element_text:
                        target_element_idx = i
                        target_original = original_text
                        target_info = info
                        break
                if target_element_idx is not None:
                    break

        if target_element_idx is None:
            # No replacements found in this TJ array
            return [([tj_array], operator)]

        # Execute precision width matching replacement
        split_operations = self._execute_precision_width_replacement(
            tj_array, target_element_idx, target_original, target_info, segment, run_id
        )

        # Save final stream for debugging
        self._save_debug_stream(run_id, "after_reconstruction", split_operations)

        return split_operations

    def _execute_precision_width_replacement(
        self,
        tj_array: ArrayObject,
        element_idx: int,
        original_text: str,
        replacement_info: Dict[str, object],
        segment: Dict[str, object],
        run_id: Optional[str] = None,
    ) -> List[Tuple[List[object], bytes]]:
        """
        Execute precision width matching replacement with TJ operator splitting.
        """
        replacement_text = replacement_info['replacement']
        original_width = replacement_info['original_width']
        original_font_size = replacement_info['font_size']

        if run_id:
            self.logger.info(
                f"Precision replacement: '{original_text}' -> '{replacement_text}' "
                f"(width: {original_width}pt, font: {original_font_size}pt)",
                extra={"run_id": run_id}
            )

        # Step 1: Intelligent Courier font size selection
        # Strategy: For shorter replacements, use original font size to maintain visual consistency
        #           For longer replacements, scale down intelligently to fit
        replacement_length = len(replacement_text)
        original_length = len(original_text)

        if replacement_length <= original_length:
            # Replacement is shorter or equal - use original font size for visual consistency
            # Then adjust spacing to position suffix correctly
            courier_font_size = original_font_size
            if run_id:
                self.logger.info(
                    f"Using original font size {courier_font_size:.2f}pt for shorter/equal replacement",
                    extra={"run_id": run_id}
                )
        else:
            # Replacement is longer - use intelligent scaling
            courier_font_size = self.calculate_courier_font_size(replacement_text, original_width, original_text)
            if run_id:
                self.logger.info(
                    f"Calculated scaled font size {courier_font_size:.2f}pt for longer replacement",
                    extra={"run_id": run_id}
                )

        # Step 2: Calculate spacing adjustment to position suffix exactly where it should be
        actual_replacement_width = self.calculate_text_width_courier(replacement_text, courier_font_size)
        width_difference = original_width - actual_replacement_width

        # Add spacing adjustment to position suffix correctly
        # Positive width_difference means we need to add space (replacement is narrower)
        # Negative width_difference means replacement is wider (will overlap, but that's expected for longer text)
        spacing_adjustment = 0.0
        if abs(width_difference) > 0.1:  # Add spacing for any significant difference
            # In PDF text space, NEGATIVE values move RIGHT (add space), POSITIVE moves LEFT (reduce space)
            # TJ operator uses values in 1/1000 of font size units
            # CRITICAL FIX: Negate the value because PDF TJ operator has inverted polarity
            spacing_adjustment = -(width_difference * 1000) / courier_font_size

        if run_id:
            self.logger.info(
                f"Width matching: Courier {courier_font_size:.2f}pt -> {actual_replacement_width:.2f}pt, "
                f"width_diff: {width_difference:.2f}pt, spacing: {spacing_adjustment:.2f}",
                extra={"run_id": run_id}
            )

        # Step 3: Split TJ array into prefix, replacement, suffix
        target_element = tj_array[element_idx]
        element_text = str(target_element)

        # Find exact position of target text within the element
        start_pos = element_text.find(original_text)
        if start_pos == -1:
            # Fallback if exact match not found
            return [([tj_array], b'TJ')]

        prefix_text = element_text[:start_pos]
        suffix_text = element_text[start_pos + len(original_text):]

        # Step 4: Build split operations
        operations = []

        # Part 1: Prefix elements + prefix text (if any)
        prefix_elements = list(tj_array[:element_idx])
        if prefix_text:
            prefix_elements.append(TextStringObject(prefix_text))

        if prefix_elements:
            operations.append(([ArrayObject(prefix_elements)], b'TJ'))

        # Part 2: Replacement with Courier font
        operations.extend([
            # Switch to Courier at calculated size
            ([NameObject('/Courier'), NumberObject(courier_font_size)], b'Tf'),
            # Insert replacement text
            ([ArrayObject([TextStringObject(replacement_text)])], b'TJ'),
        ])

        # Part 3: Restore original font and continue with suffix
        # Extract original font from the segment's font context (now properly captured during extraction)
        segment_font_context = segment.get('font_context', {})
        original_font_name = segment_font_context.get('font')
        actual_original_font_size = segment_font_context.get('fontsize')

        # Fallback to matched context if segment font context is not available
        if not original_font_name:
            fallback_context = replacement_info.get('context', {}).get('segment_font_context', {})
            original_font_name = fallback_context.get('font', '/F1')
            actual_original_font_size = fallback_context.get('fontsize', original_font_size)
        elif not actual_original_font_size:
            actual_original_font_size = original_font_size

        if run_id:
            self.logger.info(
                f"Font restoration: {original_font_name} @ {actual_original_font_size}pt",
                extra={"run_id": run_id}
            )

        operations.extend([
            # Restore original font from segment's actual font context
            ([NameObject(original_font_name), NumberObject(actual_original_font_size)], b'Tf'),
        ])

        # Part 4: Suffix text + remaining elements
        suffix_elements = []

        # Add spacing adjustment BEFORE suffix text to position it correctly
        if abs(spacing_adjustment) > 0.1:
            suffix_elements.append(NumberObject(spacing_adjustment))

        if suffix_text:
            suffix_elements.append(TextStringObject(suffix_text))
        suffix_elements.extend(tj_array[element_idx + 1:])

        if suffix_elements:
            operations.append(([ArrayObject(suffix_elements)], b'TJ'))

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
