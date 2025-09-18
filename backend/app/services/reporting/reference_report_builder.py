from __future__ import annotations

import json
import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import re

import fitz  # PyMuPDF
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import Color, black, red, green, blue, orange, white, gray, lightgrey
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.lib.units import inch

from ..attacks.attack_service import AttackType

logger = logging.getLogger(__name__)


@dataclass
class QuestionCrop:
    question_number: str
    image_data: bytes
    bbox: Tuple[float, float, float, float]
    width: int
    height: int
    question_data: Dict[str, Any]
    
    # Analysis data - will be populated from actual evaluation results
    evaluation_data: Optional[Dict] = None
    gold_answer: Optional[str] = None
    wrong_answer: Optional[str] = None
    attack_entities: Optional[Dict] = None


class ProfessionalReportBuilder:
    """Professional reference report builder for educators."""
    
    def __init__(self, questions: List[Dict[str, Any]], attacked_pdf_path: Path, 
                 structured_doc: Dict[str, Any], assets_dir: Path, output_path: Path,
                 attack_type: AttackType, title: str, evaluations: Optional[Dict] = None):
        self.questions = questions
        self.attacked_pdf_path = attacked_pdf_path
        self.structured_doc = structured_doc
        self.assets_dir = Path(assets_dir)
        self.output_path = Path(output_path)
        self.attack_type = attack_type
        self.title = title
        self.evaluations = evaluations
        
        # Page layout constants - improved spacing
        self.page_width, self.page_height = letter
        self.margin = 40  # Reduced margin for more content space
        self.content_width = self.page_width - 2 * self.margin
        self.panel_padding = 15  # Padding inside background panels


    def build_reference_report(self) -> bool:
        """Build the complete reference report with professional layout."""
        try:
            logger.info("[REPORT] Starting reference report generation")
            logger.info(f"[REPORT] Attack type: {self.attack_type}")
            logger.info(f"[REPORT] Questions to process: {len(self.questions)}")
            logger.info(f"[REPORT] Output path: {self.output_path}")
            
            c = canvas.Canvas(str(self.output_path), pagesize=letter)
            
            # Draw improved cover page
            logger.info("[REPORT] Creating cover page with instructions")
            self._draw_improved_cover_page(c)
            logger.info("[COVER] Cover page completed, starting new page for questions")
            c.showPage()  # Start new page for questions
            
            # Initialize question processing
            logger.info("[REPORT] Starting question pages")
            current_y = self.page_height - self.margin
            
            question_count = 0
            
            for question_data in self.questions:
                question_count += 1
                q_number = question_data.get('q_number', question_count)
                logger.info(f"[REPORT] Processing Q{q_number} ({question_count}/{len(self.questions)})")
                
                # Extract high-resolution question crop
                crop = self._extract_full_width_question_crop(question_data)
                if not crop:
                    logger.warning(f"[REPORT] Q{q_number}: No crop generated, skipping question")
                    continue
                
                # Calculate space needed for this question with background panel
                needed_height = self._calculate_panel_height(crop)
                logger.info(f"[REPORT] Q{q_number}: needed_height={needed_height}, current_y={current_y}")
                
                # Check if we need a new page
                if current_y - needed_height < self.margin:
                    logger.info(f"[REPORT] Q{q_number}: Starting new page (insufficient space)")
                    c.showPage()
                    current_y = self.page_height - self.margin
                
                # Draw the question with background panel
                logger.info(f"[REPORT] Q{q_number}: Drawing question on page")
                new_y = self._draw_question_with_panel(c, crop, current_y)
                logger.info(f"[REPORT] Q{q_number}: drawn, new_y={new_y}")
                current_y = new_y - 25  # Spacing between question panels
                
            c.save()
            logger.info(f"[REPORT] Professional reference report saved to {self.output_path}")
            return True
            
        except Exception as e:
            logger.error(f"[REPORT] Failed to build reference report: {e}")
            return self._create_fallback_report()

    def _draw_improved_cover_page(self, c: canvas.Canvas):
        """Draw professional cover page with better spacing and formatting."""
        logger.info("[COVER] Drawing improved professional cover page")
        
        # Page margins and layout
        margin = self.margin
        content_width = self.content_width
        
        # Title section - improved
        c.setFillColor(Color(0.1, 0.2, 0.4))  # Dark blue
        c.setFont("Helvetica-Bold", 24)
        title_y = self.page_height - 100
        
        # Draw title with better positioning
        title_text = "Vulnerability Assessment Report"
        title_width = c.stringWidth(title_text, "Helvetica-Bold", 24)
        c.drawString((self.page_width - title_width) / 2, title_y, title_text)
        
        # Subtitle with assessment title
        c.setFont("Helvetica", 16)
        c.setFillColor(Color(0.3, 0.3, 0.3))
        subtitle_y = title_y - 40
        if self.title:
            # Clean up title text
            clean_title = self.title.replace("Term:", "").replace("Subject:", "").replace("Number:", "").strip()
            clean_title = re.sub(r'\s+', ' ', clean_title)  # Remove extra spaces
            subtitle_width = c.stringWidth(clean_title, "Helvetica", 16)
            c.drawString((self.page_width - subtitle_width) / 2, subtitle_y, clean_title)
        
        # Attack type information - improved layout
        info_y = subtitle_y - 80
        c.setFillColor(Color(0.9, 0.95, 1.0))  # Light blue background
        c.rect(margin, info_y - 60, content_width, 80, fill=1, stroke=1)
        
        c.setFillColor(Color(0.2, 0.2, 0.6))
        c.setFont("Helvetica-Bold", 14)
        c.drawString(margin + 20, info_y - 20, f"Attack Type: {self.attack_type.value}")
        
        c.setFont("Helvetica", 12)
        c.setFillColor(Color(0.4, 0.4, 0.4))
        c.drawString(margin + 20, info_y - 40, f"Report Generated: {self._get_current_timestamp()}")
        
        # Instructions section - improved formatting
        instructions_y = info_y - 120
        c.setFillColor(Color(0.1, 0.1, 0.1))
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, instructions_y, "How to Use This Report")
        
        # Instruction items with better spacing
        c.setFont("Helvetica", 11)
        c.setFillColor(Color(0.2, 0.2, 0.2))
        
        instructions = [
            "• Each question shows the manipulated version as seen by AI systems",
            "• Visual attacks may be highlighted with colored overlays or markers", 
            "• Review the analysis table for detection strategies and expected responses",
            "• Compare student submissions against the patterns described",
            "• Look for signs of AI-generated or template-based responses"
        ]
        
        instruction_y = instructions_y - 30
        for instruction in instructions:
            c.drawString(margin + 10, instruction_y, instruction)
            instruction_y -= 18
        
        # Footer with better positioning
        footer_y = self.margin + 40
        c.setFont("Helvetica", 10)
        c.setFillColor(Color(0.6, 0.6, 0.6))
        footer_text = "FairTest AI - Vulnerability Assessment Tool"
        footer_width = c.stringWidth(footer_text, "Helvetica", 10)
        c.drawString((self.page_width - footer_width) / 2, footer_y, footer_text)

    def _extract_full_width_question_crop(self, question_data: Dict[str, Any]) -> Optional[QuestionCrop]:
        """Extract full-width, high-resolution question crop with improved boundary detection."""
        context_ids = question_data.get('context_ids', [])
        q_number = question_data.get('q_number', '?')
        
        logger.info(f"[CROP] Q{q_number}: Starting full-width crop extraction with {len(context_ids)} context_ids: {context_ids}")
        
        if not context_ids:
            logger.warning(f"[CROP] Q{q_number}: No context_ids found, using fallback")
            return self._create_fallback_crop(question_data)
            
        if not self.attacked_pdf_path.exists():
            logger.error(f"[CROP] Q{q_number}: Attacked PDF not found at {self.attacked_pdf_path}")
            return None

        try:
            # Calculate improved bounding box with smarter boundaries
            min_x, min_y, max_x, max_y = float('inf'), float('inf'), 0, 0
            found_contexts = 0
            
            logger.info(f"[CROP] Q{q_number}: Searching for context_ids in document pages")
            
            # Look in pages structure
            pages = self.structured_doc.get('document', {}).get('pages', [])
            logger.info(f"[CROP] Q{q_number}: Found {len(pages)} pages to search")
            
            for page_idx, page in enumerate(pages):
                items = page.get('items', [])
                logger.info(f"[CROP] Q{q_number}: Page {page_idx} has {len(items)} items")
                
                for item in items:
                    item_id = item.get('id', '')
                    if item_id in context_ids:
                        bbox = item.get('bbox', [])
                        if len(bbox) >= 4:
                            found_contexts += 1
                            item_x1, item_y1, item_x2, item_y2 = bbox[0], bbox[1], bbox[2], bbox[3]
                            
                            min_x = min(min_x, item_x1)
                            min_y = min(min_y, item_y1) 
                            max_x = max(max_x, item_x2)
                            max_y = max(max_y, item_y2)
                            
                            logger.info(f"[CROP] Q{q_number}: Found context {item_id} at bbox({item_x1:.1f}, {item_y1:.1f}, {item_x2:.1f}, {item_y2:.1f})")
            
            if found_contexts == 0:
                logger.error(f"[CROP] Q{q_number}: No valid context items found for context_ids {context_ids}")
                return self._create_fallback_crop(question_data)
                
            # Get PDF page dimensions to use full width
            pdf_doc = fitz.open(str(self.attacked_pdf_path))
            target_page = 1 if len(pdf_doc) > 1 else 0
            page = pdf_doc[target_page]
            page_rect = page.rect
            
            # Use full PDF width with smart vertical boundaries
            # Shift crop area upward to capture question start properly
            line_height_approx = 15  # Approximate line height in PDF units
            padding_y = 5  # Minimal vertical padding to prevent bleed
            
            final_bbox = (
                page_rect.x0,  # Use full width from left edge
                max(page_rect.y0, min_y - line_height_approx - padding_y),  # Shift up by ~1 line + padding
                page_rect.x1,  # Use full width to right edge  
                min(page_rect.y1, max_y - line_height_approx + padding_y)   # Reduce bottom to compensate
            )
            
            logger.info(f"[CROP] Q{q_number}: Full-width bbox from {found_contexts} context_ids: {final_bbox}")
            logger.info(f"[CROP] Q{q_number}: PDF page dimensions: {page_rect.width}x{page_rect.height}")
            
            # Extract high-resolution crop
            crop_rect = fitz.Rect(final_bbox[0], final_bbox[1], final_bbox[2], final_bbox[3])
            crop_rect = crop_rect & page_rect  # Ensure within bounds
            
            logger.info(f"[CROP] Q{q_number}: Final crop_rect: {crop_rect}")
            
            # Use higher resolution matrix for crisp text
            mat = fitz.Matrix(3.0, 3.0)  # 3x scaling for high quality
            pix = page.get_pixmap(matrix=mat, clip=crop_rect)
            img_data = pix.tobytes("png")
            
            logger.info(f"[CROP] Q{q_number}: Extracted high-res image: {pix.width}x{pix.height} pixels, {len(img_data)} bytes")
            
            pdf_doc.close()
            
            # Create crop with evaluation data
            crop = QuestionCrop(
                question_number=q_number,
                image_data=img_data,
                bbox=final_bbox,
                width=pix.width,
                height=pix.height,
                question_data=question_data
            )
            
            # Populate evaluation and analysis data
            self._populate_crop_analysis_data(crop, question_data)
            
            return crop
            
        except Exception as e:
            logger.error(f"[CROP] Q{q_number}: Failed to extract full-width crop: {e}")
            return self._create_fallback_crop(question_data)

    def _populate_crop_analysis_data(self, crop: QuestionCrop, question_data: Dict[str, Any]):
        """Populate crop with actual evaluation data and analysis information."""
        q_number = crop.question_number
        
        # Extract actual question data
        crop.gold_answer = question_data.get('gold_answer') or question_data.get('correct_answer')
        crop.wrong_answer = question_data.get('wrong_answer') or question_data.get('wrong_label')
        
        # Extract attack entities for highlighting
        if self.attack_type == AttackType.CODE_GLYPH:
            crop.attack_entities = question_data.get('code_glyph_entities', {})
        
        # Extract evaluation data if available
        if self.evaluations:
            # Support both flat per_question map and nested structures
            try:
                per_q = self.evaluations.get("per_question") if isinstance(self.evaluations, dict) else None
                key = str(q_number)
                if isinstance(per_q, dict) and key in per_q:
                    crop.evaluation_data = per_q.get(key) or {}
                elif isinstance(self.evaluations, dict) and key in self.evaluations:
                    crop.evaluation_data = self.evaluations.get(key) or {}
            except Exception:
                pass
        
        logger.info(f"[DATA] Q{q_number}: gold_answer={crop.gold_answer}, wrong_answer={crop.wrong_answer}")
        logger.info(f"[DATA] Q{q_number}: attack_entities={crop.attack_entities}")

    def _create_fallback_crop(self, question_data: Dict[str, Any]) -> Optional[QuestionCrop]:
        """Create fallback crop when context_ids fail."""
        q_number = question_data.get('q_number', '?')
        logger.info(f"[FALLBACK] Q{q_number}: Creating fallback crop")
        
        try:
            # Create a simple text-based crop as fallback
            try:
                from PIL import Image, ImageDraw, ImageFont
                import io
            except ImportError:
                logger.warning(f"[FALLBACK] Q{q_number}: PIL not available, using minimal fallback")
                return None
            
            # Create fallback image
            img_width, img_height = 800, 100
            img = Image.new('RGB', (img_width, img_height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Draw question text
            stem_text = question_data.get('stem_text', 'Question text not available')[:100] + "..."
            draw.text((10, 20), f"Q{q_number}: {stem_text}", fill='black')
            draw.text((10, 50), "[Fallback: Original crop unavailable]", fill='red')
            
            # Convert to bytes
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_data = img_buffer.getvalue()
            
            crop = QuestionCrop(
                question_number=q_number,
                image_data=img_data,
                bbox=(0, 0, img_width, img_height),
                width=img_width,
                height=img_height,
                question_data=question_data
            )
            
            self._populate_crop_analysis_data(crop, question_data)
            return crop
            
        except Exception as e:
            logger.error(f"[FALLBACK] Q{q_number}: Failed to create fallback crop: {e}")
            return None

    def _calculate_panel_height(self, crop: QuestionCrop) -> float:
        """Calculate total height needed for question panel including background."""
        logger.info(f"[CALC] Q{crop.question_number}: Calculating panel height requirements")
        
        # Panel padding
        panel_padding = self.panel_padding * 2  # Top and bottom
        
        # Image crop height (maintain aspect ratio but limit max height)
        max_crop_height = 200  # Increased for better readability
        aspect_ratio = crop.width / crop.height if crop.height > 0 else 1
        crop_display_width = self.content_width - (self.panel_padding * 2)
        crop_height = min(max_crop_height, crop_display_width / aspect_ratio)
        
        # Analysis table height (based on actual content)
        table_height = self._calculate_table_height(crop)
        
        # Spacing between sections
        section_spacing = 20
        
        # No separate highlighting height needed since it's now in the table
        total_height = panel_padding + crop_height + section_spacing + table_height + panel_padding
        logger.info(f"[CALC] Q{crop.question_number}: panel_padding={panel_padding}, crop={crop_height}, table={table_height}, total={total_height}")
        
        return total_height

    def _calculate_table_height(self, crop: QuestionCrop) -> float:
        """Calculate height needed for analysis table based on content."""
        if not crop.gold_answer and not crop.wrong_answer and not crop.evaluation_data:
            return 80  # Minimal height for "No analysis data" message
        
        # Header row + data rows + spacing
        header_height = 25
        row_height = 60  # Adequate for wrapped text
        return header_height + row_height + 10  # 10 for spacing

    def _draw_question_with_panel(self, c: canvas.Canvas, crop: QuestionCrop, start_y: float) -> float:
        """Draw complete question section with styled background panel."""
        logger.info(f"[DRAW] Q{crop.question_number}: Starting question panel at y={start_y}")
        
        # Calculate panel dimensions
        panel_height = self._calculate_panel_height(crop)
        panel_y = start_y - panel_height
        
        # Draw background panel with subtle styling
        c.setFillColor(Color(0.98, 0.98, 1.0))  # Very light blue background
        c.setStrokeColor(Color(0.8, 0.8, 0.9))  # Light border
        c.rect(self.margin, panel_y, self.content_width, panel_height, fill=1, stroke=1)
        
        # Draw subtle header bar
        header_height = 8
        c.setFillColor(Color(0.2, 0.3, 0.6))  # Dark blue header
        c.rect(self.margin, start_y - header_height, self.content_width, header_height, fill=1, stroke=0)
        
        current_y = start_y - header_height - self.panel_padding
        logger.info(f"[DRAW] Q{crop.question_number}: Panel background drawn, content starts at y={current_y}")
        
        # Draw question image crop with entity highlighting
        logger.info(f"[DRAW] Q{crop.question_number}: Drawing full-width question crop")
        current_y = self._draw_full_width_crop_with_highlighting(c, crop, current_y)
        logger.info(f"[DRAW] Q{crop.question_number}: Image crop drawn, y={current_y}")
        
        # Add spacing before table
        current_y -= 20
        
        # Draw analysis table with real data
        logger.info(f"[DRAW] Q{crop.question_number}: Drawing analysis table")
        current_y = self._draw_improved_analysis_table(c, crop, current_y)
        logger.info(f"[DRAW] Q{crop.question_number}: Analysis table drawn, y={current_y}")
        
        final_y = panel_y
        logger.info(f"[DRAW] Q{crop.question_number}: Question panel completed, final_y={final_y}")
        return final_y
    
    def _draw_full_width_crop_with_highlighting(self, c: canvas.Canvas, crop: QuestionCrop, start_y: float) -> float:
        """Draw the full-width question image crop with entity highlighting overlays."""
        try:
            logger.info(f"[DRAW] Q{crop.question_number}: Drawing full-width crop {crop.width}x{crop.height}")
            
            # Calculate display dimensions - maintain aspect ratio, use full content width
            display_width = self.content_width - (self.panel_padding * 2)
            aspect_ratio = crop.width / crop.height if crop.height > 0 else 1
            display_height = display_width / aspect_ratio
            
            # Limit maximum height for readability
            max_height = 200
            if display_height > max_height:
                display_height = max_height
                display_width = display_height * aspect_ratio
            
            # Create temporary image file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                tmp_file.write(crop.image_data)
                tmp_path = tmp_file.name
            
            draw_x = self.margin + self.panel_padding
            draw_y = start_y - display_height
            
            logger.info(f"[DRAW] Q{crop.question_number}: Drawing at ({draw_x}, {draw_y}) size {display_width}x{display_height}")
            
            # Draw image
            c.drawImage(tmp_path, draw_x, draw_y, width=display_width, height=display_height)
            
            # Entity highlighting now handled in table instead of overlays
            
            # Clean up temp file
            import os
            os.unlink(tmp_path)
            
            logger.info(f"[DRAW] Q{crop.question_number}: Full-width crop drawn successfully")
            return draw_y
            
        except Exception as e:
            logger.error(f"[DRAW] Q{crop.question_number}: Failed to draw crop: {e}")
            # Draw placeholder with error message
            display_height = 100
            draw_y = start_y - display_height
            
            c.setFillColor(Color(0.95, 0.95, 0.95))
            c.rect(self.margin + self.panel_padding, draw_y, display_width, display_height, fill=1, stroke=1)
            c.setFillColor(Color(0.6, 0.6, 0.6))
            c.setFont("Helvetica", 12)
            c.drawString(self.margin + self.panel_padding + 10, draw_y + display_height/2, 
                        f"Question {crop.question_number} Image (Error loading)")
            return draw_y

    def _draw_entity_highlighting(self, c: canvas.Canvas, crop: QuestionCrop, 
                                crop_x: float, crop_y: float, crop_width: float, crop_height: float):
        """Draw highlighting overlays for attacked entities."""
        try:
            logger.info(f"[HIGHLIGHT] Q{crop.question_number}: Adding entity highlighting")
            
            # Get entity information
            entities = crop.attack_entities or {}
            logger.info(f"[HIGHLIGHT] Q{crop.question_number}: Raw entities: {entities}")
            
            input_entity = ""
            output_entity = ""
            
            # Try different ways to access entity data
            if isinstance(entities, dict):
                if 'entities' in entities:
                    # Format: {'entities': {'input_entity': 'X', 'output_entity': 'Y'}}
                    entity_info = entities['entities']
                    input_entity = entity_info.get('input_entity', '')
                    output_entity = entity_info.get('output_entity', '')
                else:
                    # Format: {'input_entity': 'X', 'output_entity': 'Y'}
                    input_entity = entities.get('input_entity', '')
                    output_entity = entities.get('output_entity', '')
            
            logger.info(f"[HIGHLIGHT] Q{crop.question_number}: Extracted input='{input_entity}', output='{output_entity}'")
            
            if not input_entity:
                logger.warning(f"[HIGHLIGHT] Q{crop.question_number}: No input_entity found")
                return
            
            logger.info(f"[HIGHLIGHT] Q{crop.question_number}: Drawing highlight for '{input_entity}' → '{output_entity}'")
            
            # Draw a prominent highlight box above the image
            highlight_height = 25
            highlight_y = crop_y + crop_height + 5  # Position above the image
            
            # Draw bright yellow background
            c.setFillColor(Color(1.0, 1.0, 0.0))  # Bright yellow
            c.setStrokeColor(Color(0.8, 0.6, 0.0))  # Orange border
            c.rect(crop_x, highlight_y, crop_width, highlight_height, fill=1, stroke=1)
            
            # Add clear legend text
            c.setFillColor(Color(0.0, 0.0, 0.0))  # Black text
            c.setFont("Helvetica-Bold", 10)
            legend_text = f"ATTACKED: '{input_entity}' → '{output_entity}'"
            
            # Center the text
            text_width = c.stringWidth(legend_text, "Helvetica-Bold", 10)
            text_x = crop_x + (crop_width - text_width) / 2
            c.drawString(text_x, highlight_y + 8, legend_text)
            
            logger.info(f"[HIGHLIGHT] Q{crop.question_number}: Entity highlighting added successfully")
            
        except Exception as e:
            logger.error(f"[HIGHLIGHT] Q{crop.question_number}: Failed to add highlighting: {e}")

    def _draw_improved_analysis_table(self, c: canvas.Canvas, crop: QuestionCrop, start_y: float) -> float:
        """Draw analysis table with actual evaluation data or meaningful placeholders."""
        logger.info(f"[TABLE] Q{crop.question_number}: Drawing improved analysis table at y={start_y}")
        
        # Check if we have actual data to display
        has_real_data = bool(crop.gold_answer or crop.wrong_answer or crop.evaluation_data)
        
        if not has_real_data:
            # Draw table with attack analysis even if no evaluation data
            return self._draw_attack_only_table(c, crop, start_y)
        
        # Table dimensions
        table_width = self.content_width - (self.panel_padding * 2)
        col_width = table_width / 3
        row_height = 25
        data_row_height = 60
        
        table_x = self.margin + self.panel_padding
        table_y = start_y - 15
        
        logger.debug(f"[TABLE] Q{crop.question_number}: Table dimensions: {table_width}x{row_height+data_row_height}")
        
        # Header row with improved styling
        c.setFillColor(Color(0.85, 0.9, 0.95))  # Light blue header
        c.setStrokeColor(Color(0.6, 0.7, 0.8))
        
        # Draw header cells
        for i in range(3):
            c.rect(table_x + i*col_width, table_y - row_height, col_width, row_height, fill=1, stroke=1)
        
        # Header text
        c.setFillColor(Color(0.2, 0.2, 0.4))
        c.setFont("Helvetica-Bold", 10)
        headers = ["Expected Answer (OpenAI Gold)", "Attacked AI Answer", "Attack Method & Details"]
        for i, header in enumerate(headers):
            c.drawString(table_x + i*col_width + 5, table_y - 15, header)
        
        # Data row
        c.setFillColor(Color(1, 1, 1))  # White background
        for i in range(3):
            c.rect(table_x + i*col_width, table_y - row_height - data_row_height, 
                  col_width, data_row_height, fill=1, stroke=1)
        
        # Fill with actual data
        c.setFont("Helvetica", 9)
        c.setFillColor(Color(0.2, 0.2, 0.2))
        
        # Expected answer column (OpenAI Gold)
        expected_text = crop.gold_answer or "Not specified"
        self._draw_wrapped_text(c, expected_text[:80] + ("..." if len(expected_text) > 80 else ""),
                               table_x + 5, table_y - row_height - 15, col_width - 10)
        
        # Attacked AI answer column
        attacked_ai_answer = ""
        if crop.evaluation_data and isinstance(crop.evaluation_data, dict):
            # Mixed evaluation per_question payload or legacy map
            attacked_ai_answer = (
                crop.evaluation_data.get("ai_answer")
                or crop.evaluation_data.get("predicted_label")
                or ""
            )
        attacked_ai_answer = attacked_ai_answer or "Not available"
        self._draw_wrapped_text(c, attacked_ai_answer[:80] + ("..." if len(attacked_ai_answer) > 80 else ""),
                               table_x + col_width + 5, table_y - row_height - 15, col_width - 10)
        
        # Attack analysis column (includes entity highlighting info)
        attack_text = self._get_attack_analysis(crop)
        self._draw_wrapped_text(c, attack_text,
                               table_x + 2*col_width + 5, table_y - row_height - 15, col_width - 10)
        
        final_y = table_y - row_height - data_row_height
        logger.debug(f"[TABLE] Q{crop.question_number}: Improved table completed at y={final_y}")
        return final_y

    def _draw_attack_only_table(self, c: canvas.Canvas, crop: QuestionCrop, start_y: float) -> float:
        """Draw a simplified table showing only attack analysis when no evaluation data is available."""
        # Get attack analysis info
        attack_text = self._get_attack_analysis(crop)
        
        # Table dimensions
        table_width = self.content_width - (self.panel_padding * 2)
        table_height = 80
        
        table_x = self.margin + self.panel_padding
        table_y = start_y - 15
        
        # Draw table background
        c.setFillColor(Color(0.95, 0.95, 0.95))
        c.setStrokeColor(Color(0.8, 0.8, 0.8))
        c.rect(table_x, table_y - table_height, table_width, table_height, fill=1, stroke=1)
        
        # Header
        c.setFillColor(Color(0.85, 0.9, 0.95))
        c.rect(table_x, table_y - 25, table_width, 25, fill=1, stroke=1)
        
        c.setFillColor(Color(0.2, 0.2, 0.4))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(table_x + 10, table_y - 18, "Attack Method & Detection Guide")
        
        # Content
        c.setFillColor(Color(0.2, 0.2, 0.2))
        c.setFont("Helvetica", 9)
        
        if "HUMAN READS:" in attack_text and "LLM READS:" in attack_text:
            # Draw entity highlighting info
            self._draw_wrapped_text(c, attack_text, table_x + 10, table_y - 40, table_width - 20)
        else:
            # Draw placeholder message
            c.drawString(table_x + 10, table_y - 40, "No evaluation data available - run assessment to see analysis")
            c.drawString(table_x + 10, table_y - 55, attack_text)
        
        return table_y - table_height

    def _draw_no_analysis_message(self, c: canvas.Canvas, crop: QuestionCrop, start_y: float) -> float:
        """Draw a message when no analysis data is available."""
        message_height = 50
        message_y = start_y - message_height
        
        # Draw background
        c.setFillColor(Color(0.95, 0.95, 0.95))
        c.setStrokeColor(Color(0.8, 0.8, 0.8))
        c.rect(self.margin + self.panel_padding, message_y, 
               self.content_width - (self.panel_padding * 2), message_height, fill=1, stroke=1)
        
        # Draw message
        c.setFillColor(Color(0.5, 0.5, 0.5))
        c.setFont("Helvetica-Oblique", 11)
        c.drawString(self.margin + self.panel_padding + 10, message_y + 20, 
                    "No evaluation data available for this question")
        
        return message_y

    def _get_attack_analysis(self, crop: QuestionCrop) -> str:
        """Generate detailed attack analysis text showing method and relevant fields."""
        q_data = crop.question_data
        # Prefer explicit fields set upstream by routes
        attack_method = q_data.get('attack_method') or (q_data.get('attack_metadata') or {}).get('attack_method') or (q_data.get('attack_result', {}) or {}).get('attack_method', 'unknown')
        
        # Show which specific attack method was used for this question
        method_text = f"METHOD: {attack_method.upper()}\n"
        
        if attack_method == 'code_glyph':
            # Get detailed Code Glyph entity information
            entities = crop.attack_entities or {}
            input_entity = ''
            output_entity = ''
            positions = {}
            
            if isinstance(entities, dict):
                if 'entities' in entities:
                    entity_info = entities['entities']
                    input_entity = entity_info.get('input_entity', '')
                    output_entity = entity_info.get('output_entity', '')
                    positions = entities.get('positions', {})
                else:
                    input_entity = entities.get('input_entity', '')
                    output_entity = entities.get('output_entity', '')
                    positions = entities.get('positions', {})
            
            if input_entity and output_entity:
                char_pos = f"[{positions.get('char_start', '?')}-{positions.get('char_end', '?')}]" if positions else ""
                return f"{method_text}VISUAL: '{input_entity}'\nPARSED: '{output_entity}'\nPOSITION: {char_pos}\n\nLook for responses that differ from what's visually shown"
            else:
                return f"{method_text}Glyph substitution detected\nCheck for visual vs parsed differences"
                
        elif attack_method == 'hidden_text':
            # Get Hidden Text attack details
            wrong_answer = q_data.get('wrong_answer', q_data.get('wrong_label', ''))
            wrong_reason = q_data.get('wrong_reason', '')
            
            analysis = f"{method_text}HIDDEN INSTRUCTION:\n"
            if wrong_answer:
                analysis += f"Answer: {wrong_answer}\n"
            if wrong_reason:
                analysis += f"Reason: {wrong_reason[:60]}{'...' if len(wrong_reason) > 60 else ''}\n"
            analysis += "\nCheck for responses matching hidden instructions"
            return analysis
            
        elif attack_method == 'mixed':
            # Mixed attack - show both methods attempted
            cg_entities = q_data.get('code_glyph_entities', {})
            wrong_answer = q_data.get('wrong_answer', '')
            
            analysis = f"{method_text}ATTEMPTED: Code Glyph + Hidden Text\n"
            if cg_entities:
                analysis += "Primary: Glyph substitution\n"
            if wrong_answer:
                analysis += f"Fallback: Hidden instruction → {wrong_answer}\n"
            analysis += "Check for either visual or instruction-based manipulation"
            return analysis
            
        else:
            # Fallback or unknown attack
            if self.attack_type == AttackType.CODE_GLYPH:
                return f"{method_text}Visual glyph substitution\nLook for visual inconsistencies"
            elif self.attack_type in [AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP, AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION]:
                return f"{method_text}Hidden malicious instructions\nCheck for off-topic or incorrect responses"
            else:
                return f"{method_text}Review response quality and consistency"

    def _draw_wrapped_text(self, c: canvas.Canvas, text: str, x: float, y: float, max_width: float, line_height: float = 12):
        """Draw text with word wrapping within specified width."""
        if not text.strip():
            return
            
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + (" " if current_line else "") + word
            if c.stringWidth(test_line, "Helvetica", 9) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        
        # Draw lines (limit to prevent overflow)
        for i, line in enumerate(lines[:4]):
            c.drawString(x, y - i * line_height, line)

    def _get_current_timestamp(self) -> str:
        """Get current timestamp for report."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def _create_fallback_report(self) -> bool:
        """Create simple fallback report if professional version fails."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.colors import black, red
            
            c = canvas.Canvas(str(self.output_path), pagesize=letter)
            page_width, page_height = letter
            margin = 50
            
            # Title
            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(red)
            title = "Reference Report - Fallback Mode"
            title_width = c.stringWidth(title, "Helvetica-Bold", 16)
            c.drawString((page_width - title_width) / 2, page_height - 80, title)
            
            # Basic info
            c.setFont("Helvetica", 12)
            c.setFillColor(black)
            y_pos = page_height - 120
            
            c.drawString(margin, y_pos, f"Assessment: {self.title}")
            y_pos -= 25
            c.drawString(margin, y_pos, f"Attack Type: {self.attack_type.value.replace('_', ' ').title()}")
            y_pos -= 25
            c.drawString(margin, y_pos, f"Questions: {len(self.questions)}")
            y_pos -= 40
            
            # Notice
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin, y_pos, "Note: Professional report generation failed. Using simplified format.")
            y_pos -= 30
            
            # Question list
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, y_pos, "Questions Found:")
            y_pos -= 20
            
            c.setFont("Helvetica", 10)
            for i, q in enumerate(self.questions):
                if y_pos < margin + 100:  # Start new page if needed
                    c.showPage()
                    y_pos = page_height - margin
                
                q_num = q.get('q_number', str(i+1))
                q_type = q.get('q_type', 'unknown')
                stem = q.get('stem_text', 'No stem text')[:100] + "..."
                
                c.drawString(margin, y_pos, f"Q{q_num} ({q_type}): {stem}")
                y_pos -= 15
                
                # Attack info if available
                if q.get('code_glyph_entities'):
                    entities = q['code_glyph_entities'].get('entities', {})
                    if entities:
                        inp = entities.get('input_entity', '')
                        out = entities.get('output_entity', '')
                        c.setFont("Helvetica", 9)
                        c.drawString(margin + 20, y_pos, f"Entity: '{inp}' → '{out}'")
                        c.setFont("Helvetica", 10)
                        y_pos -= 12
                
                y_pos -= 10
            
            c.save()
            return True
            
        except Exception as e:
            logger.error(f"Fallback report creation failed: {e}")
            # Create minimal text file as last resort
            try:
                with open(self.output_path.with_suffix('.txt'), 'w', encoding='utf-8') as f:
                    f.write(f"REFERENCE REPORT - FALLBACK\n")
                    f.write(f"Assessment: {self.title}\n")
                    f.write(f"Attack Type: {self.attack_type.value}\n")
                    f.write(f"Questions: {len(self.questions)}\n")
                    f.write(f"Error: {e}\n")
                return True
            except:
                return False


def build_reference_report_pdf(questions: List[Dict[str, Any]], attacked_pdf_path: Path, 
                               structured_json_path: Path, assets_dir: Path, output_path: Path,
                               attack_type: AttackType, reference_answers: Optional[Dict[str, str]] = None,
                               evaluations: Optional[Dict[str, Any]] = None) -> Path:
    """Main entry point for building professional reference reports."""
    try:
        # Load structured document
        with open(structured_json_path, 'r', encoding='utf-8') as f:
            structured_doc = json.load(f)
        
        # Extract title
        title = structured_doc.get("document", {}).get("title", "Assessment")
        
        # Build professional report
        builder = ProfessionalReportBuilder(
            questions=questions,
            attacked_pdf_path=attacked_pdf_path,
            structured_doc=structured_doc,
            assets_dir=assets_dir,
            output_path=output_path,
            attack_type=attack_type,
            title=title,
            evaluations=evaluations
        )
        
        success = builder.build_reference_report()
        if success:
            logger.info(f"Professional reference report created: {output_path}")
        else:
            logger.error("Professional report generation failed")
            
        return output_path
        
    except Exception as e:
        logger.error(f"Failed to build reference report: {e}")
        # Create minimal fallback
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(f"Reference Report - Generation Failed\nError: {e}\n")
        except:
            pass
        return output_path 