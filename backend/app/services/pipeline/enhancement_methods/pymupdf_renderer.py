from __future__ import annotations

from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

from .base_renderer import BaseRenderer
from .image_overlay_renderer import ImageOverlayRenderer
from app.utils.storage_paths import method_stage_artifact_path


class PyMuPDFRenderer(BaseRenderer):
    """Redact original glyphs and insert replacement text using PyMuPDF."""

    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)

        from app.services.developer.live_logging_service import live_logging_service

        clean_mapping = {k: v for k, v in (mapping or {}).items() if k and v}
        if not clean_mapping:
            clean_mapping = self.build_mapping_from_questions(run_id)

        if not clean_mapping:
            destination.write_bytes(original_pdf.read_bytes())
            return {
                "mapping_entries": 0,
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": 0.0,
            }

        mapping_context = self.build_mapping_context(run_id) if run_id else {}

        doc = fitz.open(str(original_pdf))
        replacement_stats = self._replace_text(doc, clean_mapping, run_id, mapping_context)
        redacted_bytes = replacement_stats.get("redacted_bytes")
        base_bytes = replacement_stats.get("rewritten_bytes") or doc.tobytes()
        doc.close()

        artifacts: Dict[str, str] = {}
        if redacted_bytes:
            try:
                redacted_path = method_stage_artifact_path(
                    run_id,
                    "redaction-rewrite-overlay",
                    "after_redaction",
                )
                redacted_path.write_bytes(redacted_bytes)
                artifacts["after_redaction"] = str(redacted_path)
            except Exception:
                pass

        if base_bytes:
            try:
                rewrite_path = method_stage_artifact_path(
                    run_id,
                    "redaction-rewrite-overlay",
                    "after_rewrite",
                )
                rewrite_path.write_bytes(base_bytes)
                artifacts["after_rewrite"] = str(rewrite_path)
            except Exception:
                pass

        overlay = ImageOverlayRenderer()
        original_bytes = original_pdf.read_bytes()
        snapshots = overlay._capture_original_snapshots(
            original_bytes,
            clean_mapping,
            run_id=run_id,
            mapping_context=mapping_context,
        )
        fallback_targets = overlay._collect_overlay_targets(
            original_bytes,
            clean_mapping,
            mapping_context=mapping_context,
        )

        doc_overlay = fitz.open(stream=base_bytes, filetype="pdf")
        overlays_applied, snapshot_targets, overlay_area, page_area = overlay._apply_image_snapshots(doc_overlay, snapshots, run_id)

        if overlays_applied < snapshot_targets and fallback_targets:
            add_applied, add_targets, add_area, add_page_area = overlay._apply_text_overlays_from_rawdict(doc_overlay, clean_mapping)
            overlays_applied += add_applied
            snapshot_targets += add_targets
            overlay_area += add_area
            page_area += add_page_area

        if overlays_applied == 0:
            question_fallback = overlay._apply_question_fallback_overlays(run_id, doc_overlay)
            if question_fallback:
                overlays_applied += question_fallback
                snapshot_targets += question_fallback

        doc_overlay.save(str(destination))
        doc_overlay.close()

        artifacts["final"] = str(destination)

        visual_targets = snapshot_targets or replacement_stats["targets"]
        base_replacements = replacement_stats["replacements"]
        effectiveness = (
            min(overlays_applied / max(visual_targets, 1), 1.0)
            if visual_targets
            else (1.0 if base_replacements else 0.0)
        )
        overlay_pct = overlay_area / max(page_area, 1.0) if page_area else 0.0

        live_logging_service.emit(
            run_id,
            "pdf_creation",
            "INFO",
            "pymupdf text replacement completed",
            component=self.__class__.__name__,
            context={
                "targets": replacement_stats["targets"],
                "replacements": replacement_stats["replacements"],
                "textbox_adjustments": replacement_stats["textbox_adjustments"],
                "min_fontsize_used": replacement_stats["min_fontsize_used"],
                "overlay_applied": overlays_applied,
                "overlay_targets": snapshot_targets,
                "overlay_area_pct": round(overlay_pct, 4),
                "artifacts": artifacts,
            },
        )

        return {
            "mapping_entries": len(clean_mapping),
            "file_size_bytes": destination.stat().st_size,
            "effectiveness_score": effectiveness,
            "replacements": base_replacements,
            "textbox_adjustments": replacement_stats["textbox_adjustments"],
            "min_fontsize_used": replacement_stats["min_fontsize_used_raw"],
            "overlay_applied": overlays_applied,
            "overlay_targets": snapshot_targets,
            "overlay_area_pct": round(overlay_pct, 4),
            "raw_targets": replacement_stats["targets"],
            "artifacts": artifacts,
        }

    def _replace_text(
        self,
        doc: fitz.Document,
        mapping: Dict[str, str],
        run_id: str | None = None,
        mapping_context: Dict[str, List[Dict[str, object]]] | None = None,
    ) -> Dict[str, float | int | None]:
        total_targets = 0
        total_replacements = 0
        textbox_adjustments = 0
        min_fontsize_used: Optional[float] = None

        overlay_font = fitz.Font(fontname="helv")

        mapping_context = mapping_context or {}

        targets_by_page: Dict[int, List[Tuple[fitz.Rect, str, float, int]]] = {}
        for page in doc:
            targets = self._collect_targets(page, mapping, mapping_context)
            if targets:
                targets_by_page[page.number] = targets
                total_targets += len(targets)

        # Apply redactions first so we can capture the intermediate artifact
        for page_num, targets in targets_by_page.items():
            page = doc[page_num]
            for rect, *_ in targets:
                try:
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                except Exception:
                    pass
            try:
                page.apply_redactions(images=0)
            except Exception:
                pass

        redacted_bytes = doc.tobytes() if targets_by_page else None

        # Insert replacement text into the cleaned regions
        for page_num, targets in targets_by_page.items():
            page = doc[page_num]
            page_rect = page.rect

            for rect, replacement, fontsize, span_len in targets:
                base_rect = fitz.Rect(rect)
                if base_rect.width <= 0 or base_rect.height <= 0:
                    continue

                working_rect = fitz.Rect(base_rect)
                inset_x = working_rect.width * 0.045
                inset_y = working_rect.height * 0.08
                if inset_x > 0:
                    working_rect.x0 = max(page_rect.x0, working_rect.x0 + inset_x)
                    working_rect.x1 = min(page_rect.x1, working_rect.x1 - inset_x)
                if inset_y > 0:
                    working_rect.y0 = max(page_rect.y0, working_rect.y0 + inset_y * 0.35)
                    working_rect.y1 = min(page_rect.y1, working_rect.y1 - inset_y)
                if working_rect.x1 <= working_rect.x0 or working_rect.y1 <= working_rect.y0:
                    working_rect = fitz.Rect(base_rect)

                safe_width = max(working_rect.width * 0.96, 1e-3)
                max_height = max(working_rect.height * 0.9, 1e-3)

                unit_width = overlay_font.text_length(replacement, 1.0) or 1e-3
                max_size_by_width = safe_width / unit_width
                max_size_by_height = max_height

                initial_size = min(float(fontsize), working_rect.height * 0.95)
                length_ratio = len(replacement.strip()) / max(span_len, 1)
                if length_ratio > 1.2:
                    initial_size /= length_ratio ** 0.5

                target_size = min(initial_size, max_size_by_width, max_size_by_height)
                min_font_size = 5.5
                target_size = max(target_size, min_font_size)

                inserted = self._insert_textbox_with_fallback(
                    page,
                    working_rect,
                    replacement,
                    target_size,
                    min_font_size,
                )
                if inserted:
                    total_replacements += 1
                    min_fontsize_used = (
                        inserted
                        if min_fontsize_used is None
                        else min(min_fontsize_used, inserted)
                    )
                    if inserted < float(fontsize) - 0.25:
                        textbox_adjustments += 1
                else:
                    continue

        if run_id and not mapping_context:
            fallback_stats = self._apply_structured_question_replacements(
                doc, run_id, mapping, overlay_font
            )
            total_targets += fallback_stats["targets"]
            total_replacements += fallback_stats["replacements"]
            textbox_adjustments += fallback_stats["textbox_adjustments"]
            if fallback_stats["min_fontsize_used"] is not None:
                if min_fontsize_used is None:
                    min_fontsize_used = fallback_stats["min_fontsize_used"]
                else:
                    min_fontsize_used = min(min_fontsize_used, fallback_stats["min_fontsize_used"])

        rewritten_bytes = doc.tobytes()

        return {
            "targets": total_targets,
            "replacements": total_replacements,
            "textbox_adjustments": textbox_adjustments,
            "min_fontsize_used": None if min_fontsize_used is None else round(min_fontsize_used, 2),
            "min_fontsize_used_raw": min_fontsize_used,
            "redacted_bytes": redacted_bytes,
            "rewritten_bytes": rewritten_bytes,
        }

    def _apply_structured_question_replacements(
        self,
        doc: fitz.Document,
        run_id: str,
        mapping: Dict[str, str],
        overlay_font: fitz.Font,
    ) -> Dict[str, float | int | None]:
        structured = self.structured_manager.load(run_id)
        if not structured:
            return {"targets": 0, "replacements": 0, "textbox_adjustments": 0, "min_fontsize_used": None}

        questions = structured.get("questions", [])
        question_index = structured.get("question_index", [])
        index_by_q = {str(entry.get("q_number")): entry for entry in question_index}

        total_targets = 0
        total_replacements = 0
        textbox_adjustments = 0
        min_fontsize_used: Optional[float] = None

        for question in questions:
            manipulation = question.get("manipulation", {})
            substring_mappings = manipulation.get("substring_mappings", [])
            if not substring_mappings:
                continue

            qnum = str(question.get("q_number") or question.get("question_number"))
            index_entry = index_by_q.get(qnum, {})
            page_num = index_entry.get("page") or (question.get("positioning") or {}).get("page")
            if page_num is None:
                continue

            page_idx = int(page_num) - 1
            if page_idx < 0 or page_idx >= len(doc):
                continue

            page = doc[page_idx]

            for entry in substring_mappings[:1]:
                original = (entry or {}).get("original")
                replacement = (entry or {}).get("replacement")
                if not original or not replacement:
                    continue

                candidates = [original]
                if "?" in original:
                    candidates.append(original.split("?")[0].strip() + "?")
                candidates.append(original[:80].strip())
                candidates.append(original[:60].strip())

                rect = None
                for candidate in candidates:
                    if not candidate:
                        continue
                    rects = page.search_for(candidate)
                    if rects:
                        rect = rects[0]
                        break

                if rect is None:
                    stem_info = (index_entry.get("stem") or {})
                    bbox = stem_info.get("bbox")
                    if not bbox:
                        continue
                    rect = fitz.Rect(*bbox)

                if rect.width <= 0 or rect.height <= 0:
                    continue

                try:
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions(images=0)
                except Exception:
                    pass

                working_rect = fitz.Rect(rect)
                inset_x = working_rect.width * 0.04
                inset_y = working_rect.height * 0.08
                if inset_x > 0:
                    working_rect.x0 = max(page.rect.x0, working_rect.x0 + inset_x)
                    working_rect.x1 = min(page.rect.x1, working_rect.x1 - inset_x)
                if inset_y > 0:
                    working_rect.y0 = max(page.rect.y0, working_rect.y0 + inset_y * 0.35)
                    working_rect.y1 = min(page.rect.y1, working_rect.y1 - inset_y)
                if working_rect.x1 <= working_rect.x0 or working_rect.y1 <= working_rect.y0:
                    working_rect = fitz.Rect(rect)

                safe_width = max(working_rect.width * 0.96, 1e-3)
                max_height = max(working_rect.height * 0.9, 1e-3)
                unit_width = overlay_font.text_length(replacement, 1.0) or 1e-3
                max_size_by_width = safe_width / unit_width
                max_size_by_height = max_height
                initial_size = min(working_rect.height * 0.9, max_height)
                target_size = min(initial_size, max_size_by_width, max_size_by_height)
                target_size = max(target_size, 5.5)

                try:
                    page.insert_textbox(
                        working_rect,
                        replacement,
                        fontsize=target_size,
                        fontname="helv",
                        color=(0, 0, 0),
                        align=1,
                    )
                    total_targets += 1
                    total_replacements += 1
                    if target_size < initial_size:
                        textbox_adjustments += 1
                    if min_fontsize_used is None:
                        min_fontsize_used = target_size
                    else:
                        min_fontsize_used = min(min_fontsize_used, target_size)
                except Exception:
                    continue

        return {
            "targets": total_targets,
            "replacements": total_replacements,
            "textbox_adjustments": textbox_adjustments,
            "min_fontsize_used": min_fontsize_used,
        }

    def _collect_targets(
        self,
        page: fitz.Page,
        mapping: Dict[str, str],
        context_map: Dict[str, List[Dict[str, object]]],
    ) -> List[Tuple[fitz.Rect, str, float, int]]:
        targets: List[Tuple[fitz.Rect, str, float, int]] = []
        pairs = self.expand_mapping_pairs(mapping)
        if not pairs:
            return targets

        grouped: "OrderedDict[str, List[str]]" = OrderedDict()
        for original, replacement in pairs:
            grouped.setdefault(original, []).append(replacement)

        used_rects: List[fitz.Rect] = []
        used_counts: Dict[str, int] = defaultdict(int)

        # First, honor structured contexts so we only touch the intended regions
        page_contexts: List[Dict[str, object]] = []
        for entries in context_map.values():
            for ctx in entries:
                if ctx.get("page") == page.number:
                    page_contexts.append(ctx)

        if page_contexts:
            page_contexts.sort(
                key=lambda ctx: (
                    ctx.get("start_pos", float("inf")),
                    ctx.get("entry_index", 0),
                )
            )

            for ctx in page_contexts:
                location = self.locate_text_span(page, ctx, used_rects)
                if not location:
                    continue
                rect, fontsize, span_len = location
                used_rects.append(rect)
                original = str(ctx.get("original") or "")
                replacement_text = str(ctx.get("replacement") or "")
                used_counts[original] += 1
                targets.append((rect, replacement_text, fontsize, span_len))

        # Fallback: handle any remaining mapping entries not covered by structured data
        for original, replacements in grouped.items():
            remaining = len(replacements) - used_counts.get(original, 0)
            if remaining <= 0:
                continue

            occurrences = self._find_occurrences(page, original)
            for rect, fontsize, span_len in occurrences:
                if remaining <= 0:
                    break
                if self._rects_conflict(rect, used_rects):
                    continue
                used_rects.append(rect)
                replacement = replacements[len(replacements) - remaining]
                targets.append((rect, replacement, fontsize, span_len))
                remaining -= 1

        return targets

    def _insert_textbox_with_fallback(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        text: str,
        initial_size: float,
        min_font_size: float,
    ) -> float | None:
        """Attempt to insert text, retrying with adjusted size/rect when necessary."""
        page_rect = page.rect
        attempt_rect = fitz.Rect(rect)
        attempt_size = float(initial_size)

        for attempt in range(3):
            try:
                result = page.insert_textbox(
                    attempt_rect,
                    text,
                    fontsize=attempt_size,
                    fontname="helv",
                    color=(0, 0, 0),
                    align=1,
                )
            except Exception:
                result = -1

            if result is not None and result >= 0:
                return attempt_size

            if attempt == 0:
                attempt_size = max(attempt_size * 0.85, min_font_size)
            elif attempt == 1:
                expand_w = max(attempt_rect.width * 0.15, 1.0)
                expand_h = max(attempt_rect.height * 0.2, 1.0)
                attempt_rect = fitz.Rect(
                    max(page_rect.x0, attempt_rect.x0 - expand_w),
                    max(page_rect.y0, attempt_rect.y0 - expand_h),
                    min(page_rect.x1, attempt_rect.x1 + expand_w),
                    min(page_rect.y1, attempt_rect.y1 + expand_h),
                )
                attempt_size = max(attempt_size * 0.9, min_font_size)
            else:
                attempt_size = max(attempt_size * 0.9, min_font_size)

        return None

    def _find_occurrences(
        self,
        page: fitz.Page,
        needle: str,
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
                        rect = fitz.Rect(chars[idx]["bbox"])
                        for ch in chars[idx + 1 : end]:
                            rect |= fitz.Rect(ch.get("bbox", rect))
                        span_bbox = span.get("bbox")
                        if span_bbox and len(span_bbox) == 4:
                            rect.y0 = min(rect.y0, float(span_bbox[1]))
                            rect.y1 = max(rect.y1, float(span_bbox[3]))
                        fontsize = float(span.get("size", 10.0))
                        span_len = end - idx
                        results.append((rect, fontsize, span_len))
                        start = end

        return results
