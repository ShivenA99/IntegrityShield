from __future__ import annotations

from abc import ABC
from collections import OrderedDict, defaultdict
import copy
import hashlib
import io
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
from ....models.pipeline import QuestionManipulation
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

        def process_question(q_label: str, structured_entry: Optional[dict], model: Optional[QuestionManipulation]) -> None:
            if not q_label:
                return
            try:
                payload = self._assemble_question_payload(
                    q_label,
                    structured_entry or {},
                    index_by_q.get(q_label, {}),
                    model,
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

        if substring_mappings and page_idx is None:
            raise ValueError(
                f"Question {q_label} missing page index for deterministic matching"
            )

        if substring_mappings and not bbox:
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
            }

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
        SPACE_THRESHOLD = -80.0

        for op_index, (operands, operator) in enumerate(content.operations):
            if operator == b"Tf" and len(operands) >= 1:
                font_name = operands[0]
                if isinstance(font_name, NameObject):
                    current_font = str(font_name)
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
                        "start": current_offset,
                        "end": current_offset + len(decoded),
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
                for item in array_obj:
                    if isinstance(item, (TextStringObject, ByteStringObject)):
                        decoded_parts.append(self._decode_pdf_text(item, current_font, font_cmaps))
                    elif isinstance(item, NumberObject):
                        try:
                            if float(item) <= SPACE_THRESHOLD:
                                decoded_parts.append(" ")
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
                        "start": current_offset,
                        "end": current_offset + len(decoded),
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

    def _plan_replacements(
        self,
        segments: List[Dict[str, object]],
        contexts: List[Dict[str, object]],
        used_fingerprints: set[str],
        run_id: Optional[str],
        page_index: int,
    ) -> List[Dict[str, object]]:
        combined_text = "".join(segment["text"] for segment in segments)
        replacements: List[Dict[str, object]] = []
        used_ranges: List[Tuple[int, int]] = []
        local_fingerprints: set[str] = set()

        for ctx in contexts:
            fingerprint_key = str(ctx.get("matched_fingerprint_key") or ctx.get("fingerprint_key") or "")
            if fingerprint_key and fingerprint_key in used_fingerprints:
                continue
            if fingerprint_key and fingerprint_key in local_fingerprints:
                continue

            target_text = ctx.get("matched_text") or ctx.get("original")
            replacement_text = ctx.get("replacement")
            if not target_text or not replacement_text:
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

            inserted = False
            for index, seg in enumerate(covering_segments):
                seg_start = seg["start"]
                seg_end = seg["end"]
                local_start = max(start, seg_start) - seg_start
                local_end = min(end, seg_end) - seg_start
                if local_end < local_start:
                    continue

                text_to_insert = insert_text if not inserted else ""
                edits_by_segment[id(seg)].append((local_start, local_end, text_to_insert))
                inserted = True

            replacement["applied"] = True

        for seg_id, edits in edits_by_segment.items():
            segment = segment_map.get(seg_id)
            if not segment:
                continue
            text = segment.get("text", "")
            edits.sort(key=lambda item: item[0])
            cursor = 0
            new_text_parts: List[str] = []
            for start, end, insert_text in edits:
                new_text_parts.append(text[cursor:start])
                new_text_parts.append(insert_text)
                cursor = end
            new_text_parts.append(text[cursor:])
            new_text = "".join(new_text_parts)
            if new_text != text:
                segment["new_text"] = new_text
                modified = True

        return modified

    def _rebuild_operations(
        self,
        operations: List[Tuple[List[object], bytes]],
        segments: List[Dict[str, object]],
    ) -> List[Tuple[List[object], bytes]]:
        updated = list(operations)
        for segment in segments:
            new_text = segment.get("new_text")
            if new_text is None:
                continue
            index = segment["index"]
            operator = segment["operator"]
            if operator == b"Tj":
                updated[index] = ([TextStringObject(new_text)], operator)
            elif operator == b"TJ":
                updated[index] = ([ArrayObject([TextStringObject(new_text)])], operator)
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

            replacements = self._plan_replacements(
                segments,
                matched_contexts,
                used_fingerprints,
                run_id,
                page_index,
            )

            if not replacements:
                writer.add_page(page)
                continue

            modified = self._apply_segment_edits(
                segments,
                replacements,
                run_id,
                page_index,
            )

            if modified:
                matches_found += len(replacements)
                replacements_applied += sum(1 for item in replacements if item.get("applied"))
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
                    bbox = ctx.get("stem_bbox") or ctx.get("bbox")
                    if not isinstance(page_idx, int) or not bbox or len(bbox) != 4:
                        continue

                    try:
                        rect = fitz.Rect(*bbox)
                    except Exception:
                        continue

                    expanded = fitz.Rect(rect)
                    expanded.x0 -= 2
                    expanded.y0 -= 2
                    expanded.x1 += 2
                    expanded.y1 += 2

                    if page_idx < 0 or page_idx >= len(doc):
                        continue

                    page = doc[page_idx]
                    region_text = page.get_text("text", clip=expanded) or ""
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

        clip_data = context.get("stem_bbox") or context.get("bbox")
        clip_rect = None
        if clip_data and len(clip_data) == 4:
            try:
                clip_rect = fitz.Rect(*clip_data)
            except Exception:
                clip_rect = None

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
