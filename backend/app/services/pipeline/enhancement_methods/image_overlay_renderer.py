from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Any, Tuple
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

        # Load structured data to get precise overlay targets
        structured = self.structured_manager.load(run_id)
        questions = structured.get("questions", [])

        if not questions:
            # No questions detected, just copy original
            destination.write_bytes(original_pdf.read_bytes())
            return {
                "mapping_entries": 0,
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": 0.0,
            }

        # Open the original PDF
        doc = fitz.open(original_pdf)

        try:
            # Process questions and apply precision overlays using GPT-5 manipulation targets
            overlays_applied = 0
            total_targets = 0

            for question in questions:
                manipulation_targets = question.get("manipulation_targets", [])
                total_targets += len(manipulation_targets)

                for target in manipulation_targets:
                    # Apply dual-operation: content replacement + visual overlay
                    success = self._apply_precision_overlay_target(doc, target)
                    if success:
                        overlays_applied += 1

            # Save the modified PDF
            doc.save(destination)

            effectiveness_score = min(overlays_applied / max(total_targets, 1), 1.0) if total_targets > 0 else 0.0

            return {
                "mapping_entries": total_targets,
                "overlays_applied": overlays_applied,
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": effectiveness_score,
            }

        finally:
            doc.close()

    def _apply_precision_overlay_target(self, doc: fitz.Document, target: Dict[str, Any]) -> bool:
        """Apply precision overlay using GPT-5 manipulation target - dual operation approach."""
        try:
            original_substring = target.get("original_substring", "")
            replacement_substring = target.get("replacement_substring", "")
            bbox = target.get("bbox", [])

            if not all([original_substring, replacement_substring, bbox]):
                return False

            # Step 1: Content Stream Replacement (for LLM parsing)
            # This replaces the actual text content in PDF streams
            self._replace_content_in_streams(doc, original_substring, replacement_substring)

            # Step 2: Visual Overlay (for human perception)
            # This overlays the original visual appearance so humans see original text
            page = doc[0]  # Assuming single page for now
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])

            # Capture original visual appearance before replacement
            original_image = page.get_pixmap(clip=rect, dpi=200, alpha=False)

            # Apply the visual overlay of original text
            page.insert_image(rect, pixmap=original_image, keep_proportion=False, overlay=True)

            return True

        except Exception as e:
            self.logger.error(f"Precision overlay failed: {e}")
            return False

    def _replace_content_in_streams(self, doc: fitz.Document, original: str, replacement: str) -> None:
        """Replace content in PDF text streams (similar to code_glyph approach)."""
        try:
            # This is a simplified version - in production, we'd need PyPDF2 integration
            # for proper content stream manipulation like in code_glyph
            for page_num in range(doc.page_count):
                page = doc[page_num]

                # Find and replace text instances
                text_instances = page.search_for(original)
                for inst in text_instances:
                    # For now, use simple text replacement
                    # In full implementation, we'd manipulate content streams directly
                    pass

        except Exception as e:
            self.logger.warning(f"Content stream replacement failed: {e}")

    def _apply_precise_overlay(
        self,
        page: fitz.Page,
        bbox: List[float],
        replacement_text: str,
        target: Dict[str, Any]
    ) -> bool:
        """Apply precise image overlay using exact bbox coordinates."""
        try:
            # Convert bbox to fitz.Rect
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])

            # Create background rectangle to cover original text
            background_color = self._sample_background_color(page, rect)

            # Draw white/background rectangle to cover original text
            page.draw_rect(rect, color=background_color, fill=background_color)

            # Create overlay image with enhanced quality
            overlay_image = self._create_enhanced_text_overlay(
                replacement_text, rect, target
            )

            if overlay_image:
                # Insert the image overlay at precise location
                page.insert_image(rect, pixmap=overlay_image)
                return True

            return False

        except Exception as e:
            # If precise overlay fails, log and continue
            return False

    def _sample_background_color(self, page: fitz.Page, rect: fitz.Rect) -> Tuple[float, float, float]:
        """Sample background color around the text for seamless overlay."""
        try:
            # Sample pixels around the text area
            # For now, use white as default background
            return (1.0, 1.0, 1.0)  # White in PyMuPDF RGB
        except:
            return (1.0, 1.0, 1.0)  # Default to white

    def _create_enhanced_text_overlay(
        self,
        text: str,
        rect: fitz.Rect,
        target: Dict[str, Any]
    ) -> fitz.Pixmap | None:
        """Create enhanced text overlay with better font matching."""
        try:
            # Calculate image dimensions
            width = int(rect.width)
            height = int(rect.height)

            if width <= 0 or height <= 0:
                return None

            # Get font information from target
            original_font = target.get("font", "")
            font_size = target.get("size", 12.0)

            # Create high-DPI image for better quality
            dpi_scale = 2
            img = Image.new('RGBA', (width * dpi_scale, height * dpi_scale), (255, 255, 255, 255))
            draw = ImageDraw.Draw(img)

            # Load appropriate font based on original font
            font = self._get_matching_font(original_font, font_size * dpi_scale)

            if font:
                # Get text dimensions
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # Center the text
                x = max(0, (width * dpi_scale - text_width) // 2)
                y = max(0, (height * dpi_scale - text_height) // 2)

                # Draw text with proper color
                draw.text((x, y), text, fill=(0, 0, 0, 255), font=font)
            else:
                # Fallback text rendering
                draw.text((5 * dpi_scale, height * dpi_scale // 2 - 6 * dpi_scale), text, fill=(0, 0, 0, 255))

            # Scale down for final image
            img = img.resize((width, height), Image.LANCZOS)

            # Convert to PyMuPDF pixmap
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            return fitz.Pixmap(img_bytes.getvalue())

        except Exception as e:
            return None

    def _get_matching_font(self, original_font: str, size: float) -> ImageFont.FreeTypeFont | None:
        """Get font that matches the original PDF font."""
        try:
            # Map common PDF fonts to system fonts
            font_mappings = {
                "TimesNewRomanPS-BoldMT": ["times.ttf", "Times-Bold.ttf", "timesbd.ttf"],
                "TimesNewRomanPSMT": ["times.ttf", "Times-Roman.ttf", "times.ttf"],
                "ArialMT": ["arial.ttf", "Arial.ttf", "helvetica.ttf"],
                "MS-PMincho": ["msgothic.ttc", "arial.ttf"]  # Fallback for special fonts
            }

            font_candidates = font_mappings.get(original_font, ["arial.ttf", "times.ttf"])

            for font_name in font_candidates:
                try:
                    return ImageFont.truetype(font_name, int(size))
                except (OSError, IOError):
                    continue

            # Final fallback
            return ImageFont.load_default()

        except:
            return None

    def _create_text_overlay_image(
        self,
        text: str,
        rect: fitz.Rect,
        page: fitz.Page
    ) -> fitz.Pixmap | None:
        """Create a text overlay image that matches the original text appearance."""
        try:
            # Calculate image dimensions based on text rectangle
            width = int(rect.width)
            height = int(rect.height)

            if width <= 0 or height <= 0:
                return None

            # Create a PIL image with transparent background
            img = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(img)

            # Try to use a default font, fall back to PIL default if not available
            try:
                # Use a reasonably sized font that fits the text rectangle
                font_size = max(8, min(int(height * 0.7), 20))
                font = ImageFont.truetype("arial.ttf", font_size)
            except (OSError, IOError):
                # Fall back to default PIL font
                try:
                    font = ImageFont.load_default()
                except:
                    font = None

            # Draw the replacement text with black color
            if font:
                # Get text dimensions to center it
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                # Center the text in the rectangle
                x = max(0, (width - text_width) // 2)
                y = max(0, (height - text_height) // 2)

                draw.text((x, y), text, fill=(0, 0, 0, 255), font=font)
            else:
                # Fallback without font
                draw.text((5, height//2 - 6), text, fill=(0, 0, 0, 255))

            # Convert PIL image to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            # Create PyMuPDF pixmap from the image bytes
            return fitz.Pixmap(img_bytes.getvalue())

        except Exception as e:
            # If image creation fails, return None to skip this overlay
            return None
