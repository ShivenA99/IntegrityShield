from __future__ import annotations

from abc import ABC
from collections import OrderedDict, defaultdict
import hashlib
from pathlib import Path
import re
from typing import Dict, Iterable, List, Tuple, Optional

import fitz

from ...data_management.structured_data_manager import StructuredDataManager
from ....models.pipeline import QuestionManipulation


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
        """Return per-question context for substring mappings keyed by cleaned original text."""
        contexts: "defaultdict[str, List[Dict[str, object]]]" = defaultdict(list)
        if not run_id:
            return contexts

        structured = self.structured_manager.load(run_id)
        if not structured:
            return contexts

        questions = structured.get("questions", []) or []
        question_index = structured.get("question_index", []) or []
        index_by_q = {
            str(entry.get("q_number")): entry for entry in question_index if entry.get("q_number") is not None
        }

        for question in questions:
            manipulation = question.get("manipulation", {}) or {}
            substring_mappings = manipulation.get("substring_mappings", []) or []
            if not substring_mappings:
                continue

            q_label = str(question.get("q_number") or question.get("question_number"))
            index_entry = index_by_q.get(q_label, {})
            positioning = question.get("positioning") or {}
            page = index_entry.get("page") or positioning.get("page")
            page_idx = int(page) - 1 if isinstance(page, (int, float)) else None
            stem_info = (index_entry.get("stem") or {}) if isinstance(index_entry, dict) else {}
            bbox = stem_info.get("bbox")
            stem_text_raw = question.get("stem_text") or ""
            stem_text = self.strip_zero_width(stem_text_raw)

            for entry_idx, entry in enumerate(substring_mappings):
                original_raw = (entry or {}).get("original") or ""
                replacement_raw = (entry or {}).get("replacement") or ""
                original = self.strip_zero_width(original_raw).strip()
                replacement = self.strip_zero_width(replacement_raw).strip()
                if not original or not replacement:
                    continue

                start_pos = entry.get("start_pos")
                end_pos = entry.get("end_pos")
                prefix = ""
                suffix = ""
                if stem_text and isinstance(start_pos, int) and isinstance(end_pos, int):
                    prefix = stem_text[max(0, start_pos - 12) : start_pos]
                    suffix = stem_text[end_pos : end_pos + 12]

                contexts[original].append(
                    {
                        "original": original,
                        "replacement": replacement,
                        "page": page_idx,
                        "stem_bbox": tuple(bbox) if bbox else None,
                        "q_number": q_label,
                        "entry_index": entry_idx,
                        "start_pos": start_pos,
                        "end_pos": end_pos,
                        "prefix": prefix,
                        "suffix": suffix,
                    }
                )

        return contexts

    def strip_zero_width(self, text: str | None) -> str:
        if not text:
            return ""
        return "".join(ch for ch in text if ch not in self._ZERO_WIDTH_MARKERS)

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
    ) -> List[Tuple[fitz.Rect, float, int]]:
        results: List[Tuple[fitz.Rect, float, int]] = []
        if not needle:
            return results

        needle_cf = needle.casefold()
        raw = page.get_text("rawdict") or {}
        blocks = raw.get("blocks") or []

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
                        results.append((char_rect, fontsize, span_len))
                        start = end

        # Sort by reading order (top to bottom, left to right)
        results.sort(key=lambda item: (round(item[0].y0, 3), round(item[0].x0, 3)))
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

        search_regions = [clip_rect] if clip_rect else [None]
        if clip_rect is not None:
            expanded = fitz.Rect(clip_rect)
            expanded.inflate(6)
            search_regions.append(expanded)

        for region in search_regions:
            occurrences = self._find_occurrences(page, original, region)
            for rect, fontsize, span_len in occurrences:
                if clip_rect and not rect.intersects(clip_rect):
                    continue
                if used_rects and self._rects_conflict(rect, used_rects):
                    continue
                return rect, fontsize, span_len

        return None
