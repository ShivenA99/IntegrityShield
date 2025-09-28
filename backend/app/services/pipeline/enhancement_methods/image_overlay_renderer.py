from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, Sequence
from collections import defaultdict, OrderedDict
from PIL import Image, ImageDraw, ImageFont
import fitz

from .base_renderer import BaseRenderer


class ImageOverlayRenderer(BaseRenderer):
    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)

        from ...developer.live_logging_service import live_logging_service

        # Read original PDF bytes once for all operations
        original_bytes = original_pdf.read_bytes()

        # Build enhanced mapping with discovered tokens if provided mapping is insufficient
        clean_mapping = {k: v for k, v in (mapping or {}).items() if k and v}
        if not clean_mapping:
            # Use enhanced mapping with discovered tokens
            enhanced_mapping, discovered_tokens = self.build_enhanced_mapping_with_discovery(run_id, original_bytes)
            clean_mapping = {k: v for k, v in enhanced_mapping.items() if k and v}

            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "INFO",
                "image_overlay: using enhanced mapping with discovered tokens",
                component=self.__class__.__name__,
                context={
                    "enhanced_mapping_size": len(enhanced_mapping),
                    "discovered_tokens": len(discovered_tokens),
                    "clean_mapping_size": len(clean_mapping),
                },
            )

            if not clean_mapping:
                destination.write_bytes(original_bytes)
                live_logging_service.emit(
                    run_id,
                    "pdf_creation",
                    "WARNING",
                    "image_overlay: no viable mapping found; copied original",
                    component=self.__class__.__name__,
                )
                return {
                    "mapping_entries": 0,
                    "file_size_bytes": destination.stat().st_size,
                    "effectiveness_score": 0.0,
                }

        mapping_context = self.build_mapping_context(run_id) if run_id else {}

        # Step 1: Capture precise image snapshots from original PDF before any rewriting
        try:
            original_snapshots = self._capture_original_snapshots(
                original_bytes,
                clean_mapping,
                run_id=run_id,
                mapping_context=mapping_context,
            )
            fallback_overlay_targets = self._collect_overlay_targets(original_bytes, clean_mapping)
        except Exception:
            original_snapshots = []
            fallback_overlay_targets = []

        # Step 2: Rewrite content streams using structured ops + ToUnicode (best effort)
        try:
            rewritten_bytes, text_metrics = self.rewrite_content_streams_structured(
                original_bytes,
                clean_mapping,
                mapping_context,
                run_id=run_id,
            )
        except Exception as exc:
            self.logger.warning(
                "content stream rewrite failed, using original bytes",
                extra={"run_id": run_id, "error": str(exc)},
            )
            rewritten_bytes = original_bytes
            text_metrics = {
                "pages": 0,
                "tj_hits": 0,
                "replacements": 0,
                "matches_found": 0,
                "tokens_scanned": 0,
            }

        # Step 3: Apply precision image snapshots over the rewritten PDF
        doc = fitz.open(stream=rewritten_bytes, filetype="pdf")
        try:
            # Apply captured snapshots (with real redactions first)
            overlays_applied, total_targets, overlay_area_sum, page_area_sum = self._apply_image_snapshots(
                doc, original_snapshots, run_id
            )

            # If precision snapshots didn't cover enough, fall back to legacy text overlays
            if overlays_applied < len(original_snapshots) * 0.7:  # Less than 70% success
                additional_applied, additional_targets, additional_area, additional_page_area = self._apply_text_overlays_from_rawdict(doc, clean_mapping)
                overlays_applied += additional_applied
                total_targets += additional_targets
                overlay_area_sum += additional_area
                page_area_sum += additional_page_area

            # Final fallback to word-level image overlays if still insufficient
            if overlays_applied == 0 and fallback_overlay_targets:
                by_page: Dict[int, List[Dict[str, Any]]] = {}
                for t in fallback_overlay_targets:
                    by_page.setdefault(t["page"], []).append(t)
                for page_index, targets in by_page.items():
                    if 0 <= page_index < len(doc):
                        page = doc[page_index]
                        page_area = float(page.rect.width * page.rect.height) or 1.0
                        # First add redactions for all targets on this page
                        for t in targets:
                            rect = fitz.Rect(*t["rect"])
                            try:
                                page.add_redact_annot(rect, fill=(1, 1, 1))
                            except Exception:
                                pass
                        try:
                            page.apply_redactions(images=0)
                        except Exception:
                            pass
                        # Then insert images
                        for t in targets:
                            rect = fitz.Rect(*t["rect"])
                            try:
                                page.insert_image(rect, stream=t["image"], keep_proportion=False, overlay=True)
                                overlays_applied += 1
                                total_targets += 1
                                overlay_area_sum += float(rect.width * rect.height)
                                page_area_sum += page_area
                            except Exception:
                                pass

            doc.save(destination)

            effectiveness_score = min(overlays_applied / max(total_targets, 1), 1.0) if total_targets > 0 else 0.0
            overlay_area_pct = (overlay_area_sum / max(page_area_sum, 1.0)) if page_area_sum > 0 else 0.0

            live_logging_service.emit(
                run_id,
                "pdf_creation",
                "INFO",
                "image_overlay rendering completed",
                component=self.__class__.__name__,
                context={
                    "overlays_applied": overlays_applied,
                    "total_targets": total_targets,
                    "overlay_area_pct": round(overlay_area_pct, 4),
                    "text_metrics": text_metrics,
                    "output_bytes": destination.stat().st_size,
                },
            )

            self.validate_output_with_context(
                destination.read_bytes(),
                mapping_context or {},
                run_id,
            )

            return {
                "mapping_entries": total_targets,
                "overlays_applied": overlays_applied,
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": effectiveness_score,
                "overlay_area_pct": overlay_area_pct,
                **{f"text_{k}": v for k, v in text_metrics.items()},
            }
        finally:
            doc.close()

    def _apply_image_snapshots(
        self,
        doc: fitz.Document,
        snapshots: List[Dict[str, Any]],
        run_id: str
    ) -> Tuple[int, int, float, float]:
        """Apply captured image snapshots over the rewritten PDF to preserve visual appearance.
        Now also injects an invisible replacement text layer to guarantee parseable manipulation.
        """
        overlays_applied = 0
        total_targets = len(snapshots)
        overlay_area_sum = 0.0
        page_area_sum = 0.0

        # Group snapshots by page for efficient processing
        snapshots_by_page: Dict[int, List[Dict[str, Any]]] = {}
        for snapshot in snapshots:
            page_num = snapshot.get("page", 0)
            if page_num not in snapshots_by_page:
                snapshots_by_page[page_num] = []
            snapshots_by_page[page_num].append(snapshot)

        for page_num, page_snapshots in snapshots_by_page.items():
            if page_num < 0 or page_num >= len(doc):
                continue

            page = doc[page_num]
            page_area = float(page.rect.width * page.rect.height) or 1.0

            for snapshot in page_snapshots:
                # Get the rectangle where we'll apply the snapshot
                rect_coords = snapshot.get("rect")
                if not rect_coords or len(rect_coords) != 4:
                    continue

                rect = fitz.Rect(*rect_coords)
                if not rect.is_valid or rect.is_empty:
                    continue

                image_data = snapshot.get("image_data")
                if not image_data:
                    continue

                # Optional: subtle background mask to ensure uniform background
                try:
                    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=0.95)
                except Exception:
                    pass

                # Insert the original image snapshot to preserve visual appearance
                try:
                    page.insert_image(
                        rect,
                        stream=image_data,
                        keep_proportion=False,
                        overlay=True
                    )
                    overlays_applied += 1
                    overlay_area_sum += float(rect.width * rect.height)
                    page_area_sum += page_area
                except Exception:
                    continue

                # Inject invisible replacement text so parsers/LLMs read manipulated content
                try:
                    replacement_text = snapshot.get("replacement_text") or ""
                    if replacement_text:
                        # Render invisible text within the same rect
                        page.insert_textbox(
                            rect,
                            replacement_text,
                            fontsize=10.0,
                            color=(0, 0, 0),
                            render_mode=3,  # invisible text
                            align=0,
                        )
                except Exception:
                    pass

        return overlays_applied, total_targets, overlay_area_sum, page_area_sum

    def _apply_text_overlays_from_rawdict(self, doc: fitz.Document, mapping: Dict[str, str]) -> Tuple[int, int, float, float]:
        overlays_applied = 0
        total_targets = 0
        overlay_area_sum = 0.0
        page_area_sum = 0.0

        pairs = self.expand_mapping_pairs(mapping)
        for page_index in range(len(doc)):
            page = doc[page_index]
            raw = page.get_text("rawdict") or {}
            blocks = raw.get("blocks") or []
            page_area = float(page.rect.width * page.rect.height) or 1.0

            # Collect redaction rects and deferred draws first
            to_redact: List[Tuple[fitz.Rect, float]] = []  # (rect, fontsize)
            to_draw: List[Tuple[fitz.Rect, str, float]] = []  # (rect, replacement, fontsize)

            for block in blocks:
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        span_text = span.get("text", "")
                        if not span_text:
                            continue
                        chars = span.get("chars", [])
                        if not chars:
                            # PyMuPDF may omit per-char; approximate using span bbox
                            chars = [{"bbox": span.get("bbox", page.rect), "c": c} for c in span_text]

                        span_text_cf = span_text.casefold()
                        for orig, repl in pairs:
                            if not orig:
                                continue
                            needle_cf = orig.casefold()
                            start = 0
                            while True:
                                idx = span_text_cf.find(needle_cf, start)
                                if idx == -1:
                                    break
                                end_idx = idx + len(needle_cf)
                                total_targets += 1
                                # Compute bbox union of the substring
                                try:
                                    boxes = [fitz.Rect(chars[i]["bbox"]) for i in range(idx, min(end_idx, len(chars)))]
                                    if not boxes:
                                        start = end_idx
                                        continue
                                    union = boxes[0]
                                    for b in boxes[1:]:
                                        union |= b
                                    fontsize = float(span.get("size", 10.0))
                                    # Queue redaction and draw
                                    to_redact.append((union, fontsize))
                                    to_draw.append((union, repl, fontsize))
                                except Exception:
                                    pass
                                start = end_idx

            # Apply all redactions on this page first
            if to_redact:
                for rect, _ in to_redact:
                    try:
                        page.add_redact_annot(rect, fill=(1, 1, 1))
                    except Exception:
                        pass
                try:
                    page.apply_redactions(images=0)
                except Exception:
                    pass

            # Then draw replacement text into cleaned regions
            for rect, repl, fontsize in to_draw:
                try:
                    page.insert_textbox(rect, repl, fontsize=fontsize, color=(0, 0, 0), align=0)
                    overlays_applied += 1
                    overlay_area_sum += float(rect.width * rect.height)
                    page_area_sum += page_area
                except Exception:
                    pass

        return overlays_applied, total_targets, overlay_area_sum, page_area_sum

    def _capture_original_snapshots(
        self,
        pdf_bytes: bytes,
        mapping: Dict[str, str],
        run_id: Optional[str] = None,
        mapping_context: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Capture image snapshots for replacement regions."""

        snapshots: List[Dict[str, Any]] = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        mapping_context = mapping_context or {}
        mapping_pairs = self.expand_mapping_pairs(mapping)

        try:
            used_rects: Dict[int, List[fitz.Rect]] = defaultdict(list)
            used_fingerprints: Dict[int, set[str]] = defaultdict(set)
            matched_records: List[Dict[str, object]] = []

            if mapping_context:
                contexts: List[Dict[str, Any]] = []
                for original, entries in mapping_context.items():
                    for entry in entries:
                        ctx = dict(entry)
                        ctx["original"] = ctx.get("original") or original
                        contexts.append(ctx)

                contexts.sort(
                    key=lambda ctx: (
                        ctx.get("page", 0) if isinstance(ctx.get("page"), int) else 0,
                        ctx.get("start_pos", float("inf")),
                        ctx.get("entry_index", 0),
                    )
                )

                for ctx in contexts:
                    page_idx = ctx.get("page")
                    if not isinstance(page_idx, int) or page_idx < 0 or page_idx >= len(doc):
                        continue

                    page = doc[page_idx]
                    clean_original = self.strip_zero_width(str(ctx.get("original") or "")).strip()
                    clean_replacement = self.strip_zero_width(str(ctx.get("replacement") or "")).strip()
                    if not clean_original or not clean_replacement:
                        continue

                    location = self.locate_text_span(
                        page,
                        ctx,
                        used_rects[page_idx],
                        used_fingerprints[page_idx],
                    )
                    if not location:
                        self.logger.warning(
                            "snapshot span not located",
                            extra={
                                "page": page_idx,
                                "q_number": ctx.get("q_number"),
                                "original": clean_original,
                                "fingerprint": ctx.get("fingerprint"),
                            },
                        )
                        continue
                    rect, _, _ = location

                    adjusted_rect = self._ensure_non_overlapping_rect(rect, used_rects[page_idx], page.rect)
                    if adjusted_rect is None:
                        continue

                    fingerprint_key = ctx.get("matched_fingerprint_key")
                    if fingerprint_key:
                        used_fingerprints[page_idx].add(fingerprint_key)

                    expanded_rect = adjusted_rect + [-1, -1, 1, 1]
                    try:
                        pix = page.get_pixmap(clip=expanded_rect, dpi=300, alpha=False)
                    except Exception:
                        continue

                    snapshots.append(
                        {
                            "page": page_idx,
                            "rect": tuple(expanded_rect),
                            "original_rect": tuple(adjusted_rect),
                            "original_text": clean_original,
                            "replacement_text": clean_replacement,
                            "image_data": pix.tobytes("png"),
                            "image_width": pix.width,
                            "image_height": pix.height,
                            "capture_dpi": 300,
                        }
                    )
                    matched_records.append(
                        {
                            "page": page_idx,
                            "bbox": tuple(adjusted_rect),
                            "fingerprint": ctx.get("fingerprint"),
                            "q_number": ctx.get("q_number"),
                        }
                    )

            else:
                for page_idx in range(len(doc)):
                    page = doc[page_idx]
                    for orig_text, repl_text in mapping_pairs:
                        if not orig_text:
                            continue
                        rect = self._locate_text_rect(page, orig_text)
                        if rect is None:
                            continue
                        rect = self._ensure_non_overlapping_rect(rect, used_rects[page_idx], page.rect)
                        if rect is None:
                            continue
                        expanded_rect = rect + [-1, -1, 1, 1]
                        try:
                            pix = page.get_pixmap(clip=expanded_rect, dpi=300, alpha=False)
                        except Exception:
                            continue
                        snapshots.append(
                            {
                                "page": page_idx,
                                "rect": tuple(expanded_rect),
                                "original_rect": tuple(rect),
                                "original_text": orig_text,
                                "replacement_text": repl_text,
                                "image_data": pix.tobytes("png"),
                                "image_width": pix.width,
                                "image_height": pix.height,
                                "capture_dpi": 300,
                            }
                        )

        finally:
            if 'matched_records' in locals() and matched_records:
                self.logger.info(
                    "captured %d overlay snapshots via deterministic spans",
                    len(matched_records),
                )
            doc.close()

        return snapshots

    def _clean_token(self, token: str) -> str:
        return re.sub(r"[^0-9a-z]+", "", token.casefold())

    def _locate_text_rect(
        self,
        page: fitz.Page,
        text: str,
        hint_bbox: Optional[Sequence[float]] = None,
    ) -> Optional[fitz.Rect]:
        if not text:
            return None

        normalized = unicodedata.normalize("NFKC", text)
        tokens = [self._clean_token(tok) for tok in normalized.split()]
        tokens = [tok for tok in tokens if tok]
        if not tokens:
            return None

        words = page.get_text("words") or []
        hint_rect: Optional[fitz.Rect] = None
        if hint_bbox and len(hint_bbox) == 4:
            try:
                hint_rect = fitz.Rect(*hint_bbox)
            except Exception:
                hint_rect = None

        processed: List[Tuple[fitz.Rect, str]] = []
        for x0, y0, x1, y1, word, *_ in words:
            cleaned = self._clean_token(word)
            if not cleaned:
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            if hint_rect and not rect.intersects(hint_rect):
                continue
            processed.append((rect, cleaned))

        total = len(tokens)
        for idx, (rect, token) in enumerate(processed):
            if token != tokens[0]:
                continue
            current = fitz.Rect(rect)
            j = 1
            k = idx + 1
            while j < total and k < len(processed):
                next_rect, next_token = processed[k]
                k += 1
                if next_token != tokens[j]:
                    break
                current |= next_rect
                j += 1
            if j == total:
                return current

        return None

    def _ensure_non_overlapping_rect(
        self,
        rect: fitz.Rect,
        existing: List[fitz.Rect],
        page_rect: fitz.Rect,
    ) -> Optional[fitz.Rect]:
        candidate = fitz.Rect(rect)
        attempts = 0
        vertical_shift = max(candidate.height * 0.25, 1.0)
        horizontal_shift = max(candidate.width * 0.15, 0.5)

        while any(candidate.intersects(other) for other in existing):
            attempts += 1
            if attempts <= 6:
                candidate = fitz.Rect(
                    candidate.x0,
                    candidate.y0 + vertical_shift,
                    candidate.x1,
                    candidate.y1 + vertical_shift,
                )
            else:
                candidate = fitz.Rect(
                    candidate.x0 + horizontal_shift,
                    candidate.y0,
                    candidate.x1 + horizontal_shift,
                    candidate.y1,
                )

            # Clamp within page bounds
            if candidate.x1 > page_rect.x1:
                offset = candidate.x1 - page_rect.x1
                candidate.x0 -= offset
                candidate.x1 -= offset
            if candidate.y1 > page_rect.y1:
                offset = candidate.y1 - page_rect.y1
                candidate.y0 -= offset
                candidate.y1 -= offset

            if attempts > 10:
                break

        if candidate.x0 < page_rect.x0:
            candidate.x0 = page_rect.x0
        if candidate.y0 < page_rect.y0:
            candidate.y0 = page_rect.y0

        existing.append(candidate)
        return candidate

    def _create_approximate_chars(self, text: str, bbox: List[float]) -> List[Dict[str, Any]]:
        """Create approximate character positions when chars data is missing."""
        if not text or len(bbox) != 4:
            return []

        x0, y0, x1, y1 = bbox
        char_width = (x1 - x0) / max(len(text), 1)

        chars = []
        for i, char in enumerate(text):
            char_x0 = x0 + i * char_width
            char_x1 = char_x0 + char_width
            chars.append({
                "bbox": [char_x0, y0, char_x1, y1],
                "c": char
            })

        return chars

    def _calculate_precise_rect(self, chars: List[Dict[str, Any]], start_idx: int, end_idx: int) -> Tuple[float, float, float, float] | None:
        """Calculate precise bounding rectangle from character positions."""
        if not chars or start_idx < 0 or end_idx > len(chars) or start_idx >= end_idx:
            return None

        try:
            # Get the bounding boxes for the substring
            relevant_chars = chars[start_idx:end_idx]
            if not relevant_chars:
                return None

            # Union all character bboxes
            first_bbox = relevant_chars[0].get("bbox", [0, 0, 0, 0])
            if len(first_bbox) != 4:
                return None

            min_x, min_y, max_x, max_y = first_bbox

            for char_info in relevant_chars[1:]:
                char_bbox = char_info.get("bbox", [0, 0, 0, 0])
                if len(char_bbox) == 4:
                    x0, y0, x1, y1 = char_bbox
                    min_x = min(min_x, x0)
                    min_y = min(min_y, y0)
                    max_x = max(max_x, x1)
                    max_y = max(max_y, y1)

            return (float(min_x), float(min_y), float(max_x), float(max_y))

        except (IndexError, ValueError, TypeError):
            return None

    def _is_valid_rect(self, rect: Tuple[float, float, float, float]) -> bool:
        """Check if a rectangle is valid (non-zero area and reasonable dimensions)."""
        if not rect or len(rect) != 4:
            return False

        x0, y0, x1, y1 = rect
        width = x1 - x0
        height = y1 - y0

        # Must have positive area and reasonable dimensions
        return width > 0.5 and height > 0.5 and width < 2000 and height < 2000

    def _collect_overlay_targets(
        self,
        pdf_bytes: bytes,
        mapping: Dict[str, str],
        mapping_context: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """Legacy fallback method for word-level snapshots."""
        _ = mapping_context
        targets: List[Dict[str, Any]] = []
        pairs = self.expand_mapping_pairs(mapping)
        token_exact = {orig for orig, _ in pairs}
        token_cf = {orig.casefold() for orig in token_exact}
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_number, page in enumerate(doc):
                words = page.get_text("words")
                if not words:
                    continue
                for x0, y0, x1, y1, word, *_ in words:
                    token = (word or "").strip()
                    if not token:
                        continue
                    lowered = token.casefold()
                    if token in token_exact or lowered in token_cf:
                        rect = (float(x0), float(y0), float(x1), float(y1))
                        pix = page.get_pixmap(clip=fitz.Rect(*rect), dpi=220, alpha=False)
                        targets.append({
                            "page": page_number,
                            "rect": rect,
                            "image": pix.tobytes("png"),
                        })
        finally:
            doc.close()
        return targets

    def _apply_question_fallback_overlays(self, run_id: str, doc: fitz.Document) -> int:
        structured = self.structured_manager.load(run_id)
        questions = structured.get("questions", [])
        question_index = structured.get("question_index", [])
        index_by_q = {str(q.get("q_number")): q for q in question_index}
        applied = 0

        for question in questions:
            manipulation = question.get("manipulation", {})
            substring_mappings = manipulation.get("substring_mappings", [])
            if not substring_mappings:
                continue

            qnum = str(question.get("q_number") or question.get("question_number"))
            idx = index_by_q.get(qnum, {})
            stem_info = (idx.get("stem") or {})
            stem_bbox = stem_info.get("bbox")
            page = (idx.get("page") or (question.get("positioning") or {}).get("page"))
            if stem_bbox and page is not None and isinstance(page, int) and 1 <= page <= len(doc):
                page_obj = doc[page - 1]
                rect = fitz.Rect(*stem_bbox)
                try:
                    page_obj.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), fill_opacity=0.98)
                    snapshot = page_obj.get_pixmap(clip=rect, dpi=200, alpha=False)
                    page_obj.insert_image(rect, pixmap=snapshot, keep_proportion=False, overlay=True)

                    replacements = [
                        (entry or {}).get("replacement", "")
                        for entry in substring_mappings
                        if (entry or {}).get("replacement")
                    ]
                    replacement_text = "\n".join(replacements)
                    if replacement_text:
                        try:
                            page_obj.insert_textbox(
                                rect,
                                replacement_text,
                                fontsize=10.0,
                                color=(0, 0, 0),
                                render_mode=3,
                                align=0,
                            )
                        except Exception:
                            pass

                    applied += 1
                except Exception:
                    pass
        return applied


    def _get_matching_font(self, original_font: str, size: float) -> ImageFont.FreeTypeFont | None:
        try:
            font_mappings = {
                "TimesNewRomanPS-BoldMT": ["times.ttf", "Times-Bold.ttf", "timesbd.ttf"],
                "TimesNewRomanPSMT": ["times.ttf", "Times-Roman.ttf", "times.ttf"],
                "ArialMT": ["arial.ttf", "Arial.ttf", "helvetica.ttf"],
                "MS-PMincho": ["msgothic.ttc", "arial.ttf"]
            }

            font_candidates = font_mappings.get(original_font, ["arial.ttf", "times.ttf"])

            for font_name in font_candidates:
                try:
                    return ImageFont.truetype(font_name, int(size))
                except (OSError, IOError):
                    continue

            return ImageFont.load_default()

        except Exception:
            return None
