from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional
import unicodedata

from .span_extractor import SpanRecord

Matrix = Tuple[float, float, float, float, float, float]


@dataclass
class SpanMappingRef:
    q_number: Optional[str]
    original: str
    replacement: str
    context_index: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    operator_index: Optional[int] = None
    force_courier: bool = False


@dataclass
class SpanRewriteEntry:
    page_index: int
    block_index: int
    line_index: int
    span_index: int
    operator_index: Optional[int]
    original_text: str
    replacement_text: str
    font: Optional[str]
    font_size: float
    bbox: Tuple[float, float, float, float]
    matrix: Matrix
    original_width: float
    replacement_width: float
    scale_factor: float
    mappings: List[SpanMappingRef] = field(default_factory=list)
    fragment_rewrites: List["SpanFragmentRewrite"] = field(default_factory=list)
    slice_replacements: List[Dict[str, Any]] = field(default_factory=list)
    overlay_fallback: bool = False
    requires_scaling: bool = False
    validation_failures: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SpanFragmentRewrite:
    index: int
    original_text: str
    replacement_text: str
    literal_kind: Optional[str] = None
    preserved_literal: bool = False


@dataclass
class SpanSliceReplacement:
    start: int
    end: int
    replacement: str
    mapping_ref: SpanMappingRef
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SpanRewriteAccumulator:
    span: SpanRecord
    replacements: List[SpanSliceReplacement] = field(default_factory=list)
    validation_failures: List[Dict[str, Any]] = field(default_factory=list)

    def add_replacement(
        self,
        start: int,
        end: int,
        replacement: str,
        mapping_ref: SpanMappingRef,
        *,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if end <= start:
            return
        new_start = int(start)
        new_end = int(end)
        to_remove: List[SpanSliceReplacement] = []
        for existing in self.replacements:
            existing_start = existing.start
            existing_end = existing.end
            # If the new replacement fully covers an existing one, drop the existing entry.
            if new_start <= existing_start and new_end >= existing_end:
                to_remove.append(existing)
                continue
            # If an existing replacement already covers the requested range, skip the new one.
            if existing_start <= new_start and existing_end >= new_end:
                return
            # For partial overlaps, prefer the earlier entry and ignore the new slice to avoid
            # double-application on the same operator fragment.
            overlap = not (new_end <= existing_start or new_start >= existing_end)
            if overlap:
                return
        for item in to_remove:
            try:
                self.replacements.remove(item)
            except ValueError:
                pass
        self.replacements.append(
            SpanSliceReplacement(
                start=start,
                end=end,
                replacement=replacement,
                mapping_ref=mapping_ref,
                metadata=metadata,
            )
        )

    def build_entry(
        self,
        page_index: int,
        measure_width,
        char_map,
        doc_page,
    ) -> Optional[SpanRewriteEntry]:
        if not self.replacements:
            return None

        raw_text = getattr(self.span, "text", "") or ""
        normalized_text = getattr(self.span, "normalized_text", "") or ""
        normalized_map = list(getattr(self.span, "normalized_to_raw_indices", []) or [])

        base_text = raw_text or normalized_text
        if not base_text:
            return None

        ordered = sorted(self.replacements, key=lambda item: item.start, reverse=True)
        use_raw_projection = bool(raw_text and normalized_text and len(normalized_map) == len(normalized_text))
        combined_char_map: Dict[Tuple[str, float, str], float] = {}

        def collapse(value: str) -> str:
            if not value:
                return ""
            normalized_value = unicodedata.normalize("NFKD", value)
            return "".join(ch for ch in normalized_value if not ch.isspace())

        def collapse_with_index(value: str) -> Tuple[str, List[int]]:
            collapsed: List[str] = []
            mapping: List[int] = []
            for idx, ch in enumerate(value):
                normalized_value = unicodedata.normalize("NFKD", ch) or ch
                for piece in normalized_value:
                    if piece.isspace():
                        continue
                    collapsed.append(piece)
                    mapping.append(idx)
            return "".join(collapsed), mapping

        def normalized_bounds_to_raw(start: int, end: int) -> Tuple[int, int]:
            if not use_raw_projection:
                return max(0, start), max(0, end)

            raw_len = len(base_text)
            safe_start = max(0, start)
            safe_end = max(0, end)

            if safe_start <= 0:
                raw_start = 0
            elif safe_start >= len(normalized_map):
                raw_start = raw_len
            else:
                raw_start = normalized_map[safe_start][0]

            if safe_end <= 0:
                raw_end = 0
            elif safe_end > len(normalized_map):
                raw_end = normalized_map[-1][1] if normalized_map else raw_len
            else:
                raw_end = normalized_map[safe_end - 1][1]

            raw_start = max(0, min(raw_start, raw_len))
            raw_end = max(raw_start, min(raw_end, raw_len))
            return raw_start, raw_end

        validation_failures: List[Dict[str, Any]] = []
        valid_entries: List[Tuple[SpanSliceReplacement, int, int]] = []

        for item in ordered:
            expected_original = item.mapping_ref.original or ""
            requested_start = item.start
            requested_end = item.end
            hint_start = item.mapping_ref.start
            hint_end = item.mapping_ref.end
            raw_start, raw_end = normalized_bounds_to_raw(item.start, item.end)
            observed_slice = base_text[raw_start:raw_end]

            if expected_original and collapse(observed_slice) != collapse(expected_original):
                normalized_span = normalized_text or base_text
                adjusted = False
                if normalized_span:
                    direct_idx = normalized_span.find(expected_original)
                    if direct_idx != -1:
                        item.start = direct_idx
                        item.end = direct_idx + len(expected_original)
                        raw_start, raw_end = normalized_bounds_to_raw(item.start, item.end)
                        observed_slice = base_text[raw_start:raw_end]
                        adjusted = collapse(observed_slice) == collapse(expected_original)
                    else:
                        collapsed_span, index_map = collapse_with_index(normalized_span)
                        collapsed_expected = collapse(expected_original)
                        collapsed_idx = collapsed_span.find(collapsed_expected)
                        if collapsed_idx != -1 and index_map:
                            start_idx = index_map[collapsed_idx]
                            end_idx = index_map[collapsed_idx + len(collapsed_expected) - 1] + 1
                            item.start = start_idx
                            item.end = end_idx
                            raw_start, raw_end = normalized_bounds_to_raw(item.start, item.end)
                            observed_slice = base_text[raw_start:raw_end]
                            adjusted = collapse(observed_slice) == collapse(expected_original)
                if adjusted and (
                    (hint_start is not None and hint_start != item.start)
                    or (hint_end is not None and hint_end != item.end)
                ):
                    item.start = requested_start
                    item.end = requested_end
                    raw_start, raw_end = normalized_bounds_to_raw(item.start, item.end)
                    observed_slice = base_text[raw_start:raw_end]
                    adjusted = collapse(observed_slice) == collapse(expected_original)

                if not adjusted and collapse(observed_slice) != collapse(expected_original):
                    validation_failures.append(
                        {
                            "expected": expected_original,
                            "observed": observed_slice,
                            "start": raw_start,
                            "end": raw_end,
                            "replacement": item.replacement,
                            "q_number": item.mapping_ref.q_number,
                            "operator_index": item.mapping_ref.operator_index,
                        }
                    )
                    continue

            # success path
            raw_start, raw_end = normalized_bounds_to_raw(item.start, item.end)
            valid_entries.append((item, raw_start, raw_end))

        self.validation_failures = validation_failures

        if not valid_entries:
            return None

        ordered_pairs = sorted(valid_entries, key=lambda entry: entry[0].start, reverse=True)
        ordered = [item for item, _, _ in ordered_pairs]

        replacement_text = base_text
        for item, raw_start, raw_end in ordered_pairs:
            replacement_text = (
                replacement_text[:raw_start]
                + item.replacement
                + replacement_text[raw_end:]
            )

        slice_records: List[Dict[str, Any]] = []
        overlay_flag = False
        scaling_hint = False
        for item, raw_start, raw_end in reversed(ordered_pairs):
            record: Dict[str, Any] = {
                "normalized_start": int(item.start),
                "normalized_end": int(item.end),
                "raw_start": int(raw_start),
                "raw_end": int(raw_end),
                "replacement_text": item.replacement,
            }

            metadata = item.metadata or {}
            if metadata.get("overlay_fallback"):
                overlay_flag = True
            if metadata.get("requires_scaling") or metadata.get("fragment_plan_mismatch"):
                scaling_hint = True
            char_width_map = metadata.get("char_width_map")
            if isinstance(char_width_map, dict):
                try:
                    for key, value in char_width_map.items():
                        if isinstance(key, tuple) and len(key) == 3:
                            combined_char_map[(str(key[0]), float(key[1]), str(key[2]))] = float(value)
                except Exception:
                    pass
            for key, value in metadata.items():
                if value is None or key == "char_width_map":
                    continue
                if key == "operator_fragments" and isinstance(value, list):
                    record[key] = [dict(fragment) for fragment in value]
                elif key == "span_key" and isinstance(value, tuple):
                    record[key] = list(value)
                else:
                    record[key] = value

            slice_records.append(record)

        original_width = float(self.span.bbox[2] - self.span.bbox[0]) if self.span.bbox else 0.0
        replacement_width = measure_width(
            replacement_text,
            self.span.font,
            self.span.font_size,
            self.span.bbox,
            combined_char_map,
            doc_page,
        )

        try:
            replacement_width = float(replacement_width or 0.0)
        except (TypeError, ValueError):
            replacement_width = 0.0

        scale = 1.0
        if replacement_width and original_width and replacement_width > original_width:
            scale = max(original_width / replacement_width, 0.01)
            scaling_hint = True

        mapping_refs = [item.mapping_ref for item in reversed(ordered)]
        operator_index = None
        for ref in mapping_refs:
            if ref.operator_index is not None:
                operator_index = ref.operator_index
                break

        return SpanRewriteEntry(
            page_index=page_index,
            block_index=self.span.block_index,
            line_index=self.span.line_index,
            span_index=self.span.span_index,
            operator_index=operator_index,
            original_text=base_text,
            replacement_text=replacement_text,
            font=self.span.font,
            font_size=float(self.span.font_size or 0.0),
            bbox=self.span.bbox,
            matrix=self.span.matrix,
            original_width=original_width,
            replacement_width=replacement_width,
            scale_factor=scale,
            mappings=mapping_refs,
            slice_replacements=slice_records,
            overlay_fallback=overlay_flag,
            requires_scaling=scaling_hint or (scale < 0.999 and replacement_width > 0.0),
            validation_failures=validation_failures,
        )


SpanRewriteMap = Dict[Tuple[int, int, int], SpanRewriteAccumulator]
