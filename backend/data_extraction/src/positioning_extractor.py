"""
Positioning Extractor for Granular PDF Coordinate Extraction
Extracts detailed bbox, span IDs, and text positions from PDFs using PyMuPDF
"""
import re
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF


class PositioningExtractor:
    """Extract detailed positioning data from PDF documents"""
    
    def __init__(self, pdf_path: str):
        """
        Initialize positioning extractor
        
        Args:
            pdf_path: Path to PDF file
        """
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        self.page_data = []
        self._extract_all_positioning()
    
    def _extract_all_positioning(self):
        """Extract positioning data from all pages"""
        for page_num in range(len(self.doc)):
            page = self.doc[page_num]
            page_info = {
                "page_number": page_num + 1,
                "blocks": [],
                "spans": {},
                "text_full": page.get_text()
            }
            
            # Get text with detailed span information
            text_dict = page.get_text("dict")
            
            for block_idx, block in enumerate(text_dict["blocks"]):
                if block["type"] == 0:  # Text block
                    block_data = {
                        "block_id": f"page{page_num}:block{block_idx}",
                        "bbox": block["bbox"],
                        "lines": []
                    }
                    
                    for line_idx, line in enumerate(block["lines"]):
                        line_data = {
                            "line_id": f"page{page_num}:block{block_idx}:line{line_idx}",
                            "bbox": line["bbox"],
                            "spans": []
                        }
                        
                        for span_idx, span in enumerate(line["spans"]):
                            span_id = f"page{page_num}:block{block_idx}:line{line_idx}:span{span_idx}"
                            span_data = {
                                "span_id": span_id,
                                "text": span["text"],
                                "bbox": span["bbox"],
                                "font": span["font"],
                                "size": span["size"],
                                "flags": span["flags"],
                                "color": span.get("color", 0)
                            }
                            
                            line_data["spans"].append(span_data)
                            page_info["spans"][span_id] = span_data
                        
                        block_data["lines"].append(line_data)
                    
                    page_info["blocks"].append(block_data)
            
            self.page_data.append(page_info)
    
    def find_text_position(self, text: str, page_num: int = None) -> List[Dict]:
        """
        Find position(s) of specific text in the document
        
        Args:
            text: Text to find
            page_num: Specific page to search (1-indexed), or None for all pages
            
        Returns:
            List of position dictionaries with bbox and span info
        """
        positions = []
        pages_to_search = [page_num - 1] if page_num else range(len(self.page_data))
        
        for page_idx in pages_to_search:
            if page_idx < 0 or page_idx >= len(self.page_data):
                continue
            
            page_info = self.page_data[page_idx]
            
            # Search through spans
            for block in page_info["blocks"]:
                for line in block["lines"]:
                    # Try to find text within this line
                    line_text = " ".join([s["text"] for s in line["spans"]])
                    
                    if text.lower() in line_text.lower():
                        # Found the text, now find exact span(s)
                        matching_spans = self._find_spans_for_text(text, line["spans"])
                        
                        if matching_spans:
                            # Calculate bounding box for the entire matched text
                            bbox = self._calculate_combined_bbox([s["bbox"] for s in matching_spans])
                            
                            positions.append({
                                "page": page_idx + 1,
                                "bbox": bbox,
                                "span_ids": [s["span_id"] for s in matching_spans],
                                "text": text,
                                "line_id": line["line_id"],
                                "block_id": block["block_id"]
                            })
        
        return positions
    
    def _find_spans_for_text(self, search_text: str, spans: List[Dict]) -> List[Dict]:
        """
        Find which spans contain the search text
        
        Args:
            search_text: Text to find
            spans: List of span dictionaries
            
        Returns:
            List of matching span dictionaries
        """
        search_lower = search_text.lower()
        matching_spans = []
        accumulated_text = ""
        temp_spans = []
        
        for span in spans:
            temp_spans.append(span)
            accumulated_text += span["text"]
            
            if search_lower in accumulated_text.lower():
                # Found a match
                matching_spans = temp_spans.copy()
                break
        
        return matching_spans
    
    def _calculate_combined_bbox(self, bboxes: List[List[float]]) -> List[float]:
        """
        Calculate combined bounding box from multiple bboxes
        
        Args:
            bboxes: List of [x0, y0, x1, y1] bounding boxes
            
        Returns:
            Combined [x0, y0, x1, y1] bbox
        """
        if not bboxes:
            return [0, 0, 0, 0]
        
        x0 = min(bbox[0] for bbox in bboxes)
        y0 = min(bbox[1] for bbox in bboxes)
        x1 = max(bbox[2] for bbox in bboxes)
        y1 = max(bbox[3] for bbox in bboxes)
        
        return [x0, y0, x1, y1]
    
    def extract_question_positioning(self, question_text: str, page_num: int) -> Dict:
        """
        Extract detailed positioning for an entire question
        
        Args:
            question_text: Full question text
            page_num: Page number (1-indexed)
            
        Returns:
            Dictionary with positioning data
        """
        positions = self.find_text_position(question_text, page_num)
        
        if positions:
            return positions[0]
        
        return {
            "page": page_num,
            "bbox": [0, 0, 0, 0],
            "span_ids": [],
            "text": question_text,
            "line_id": None,
            "block_id": None
        }
    
    def extract_key_term_positions(self, terms: List[str], context_text: str, page_num: int) -> Dict[str, Dict]:
        """
        Extract positions for key terms within a context
        
        Args:
            terms: List of key terms to find
            context_text: The context text where terms appear
            page_num: Page number (1-indexed)
            
        Returns:
            Dictionary mapping term -> position data
        """
        term_positions = {}
        
        for term in terms:
            positions = self.find_text_position(term, page_num)
            
            if positions:
                # Find position that's within the context
                for pos in positions:
                    term_positions[term] = {
                        "bbox": pos["bbox"],
                        "span_ids": pos["span_ids"],
                        "char_start": context_text.lower().find(term.lower()),
                        "char_end": context_text.lower().find(term.lower()) + len(term)
                    }
                    break
            else:
                # Term not found, use character positions only
                char_start = context_text.lower().find(term.lower())
                term_positions[term] = {
                    "bbox": [0, 0, 0, 0],
                    "span_ids": [],
                    "char_start": char_start,
                    "char_end": char_start + len(term) if char_start >= 0 else -1
                }
        
        return term_positions
    
    def close(self):
        """Close the PDF document"""
        if self.doc:
            self.doc.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def merge_positioning_with_structure(structured_data: Dict, pdf_path: str) -> Dict:
    """
    Merge GPT-4 Vision structured data with PyMuPDF positioning data
    
    Args:
        structured_data: Structured data from GPT-4 Vision
        pdf_path: Path to PDF file for position extraction
        
    Returns:
        Enhanced data with positioning information
    """
    try:
        with PositioningExtractor(pdf_path) as pos_extractor:
            # Process each question
            for question in structured_data.get("questions", []):
                page_num = question.get("page_number", 1)
                
                # Extract positioning for stem text
                stem_text = question.get("stem_text", "")
                if stem_text:
                    stem_pos = pos_extractor.extract_question_positioning(stem_text, page_num)
                    
                    # Update positioning field
                    if "positioning" not in question:
                        question["positioning"] = {}
                    
                    question["positioning"]["page"] = page_num
                    question["positioning"]["bbox"] = stem_pos.get("bbox", [0, 0, 0, 0])
                    question["positioning"]["stem_bbox"] = stem_pos.get("bbox", [0, 0, 0, 0])
                    question["positioning"]["stem_spans"] = stem_pos.get("span_ids", [])
                    question["positioning"]["method"] = structured_data.get("extraction_method", "gpt4_vision_with_pymupdf")
                    
                    # Extract positions for options if MCQ
                    options = question.get("options", {})
                    if options and isinstance(options, dict):
                        option_bboxes = {}
                        for option_key, option_text in options.items():
                            if option_text:
                                opt_positions = pos_extractor.find_text_position(option_text[:50], page_num)
                                if opt_positions:
                                    option_bboxes[option_key] = opt_positions[0].get("bbox", [0, 0, 0, 0])
                                else:
                                    option_bboxes[option_key] = [0, 0, 0, 0]
                        
                        question["positioning"]["option_bboxes"] = option_bboxes
                    
                    # Extract positions for key terms
                    key_terms = question.get("key_terms", [])
                    if key_terms:
                        terms_list = [kt.get("term", "") for kt in key_terms if kt.get("term")]
                        full_text = question.get("original_text", stem_text)
                        
                        term_positions = pos_extractor.extract_key_term_positions(
                            terms_list, full_text, page_num
                        )
                        
                        # Update key_terms with positioning data
                        for key_term in question.get("key_terms", []):
                            term = key_term.get("term", "")
                            if term in term_positions:
                                key_term["bbox"] = term_positions[term]["bbox"]
                                key_term["span_ids"] = term_positions[term]["span_ids"]
                                key_term["char_start"] = term_positions[term]["char_start"]
                                key_term["char_end"] = term_positions[term]["char_end"]
                
                # Set positioning quality score
                if "extraction_quality" not in question:
                    question["extraction_quality"] = {}
                
                has_valid_bbox = (
                    question.get("positioning", {}).get("bbox", [0, 0, 0, 0]) != [0, 0, 0, 0]
                )
                question["extraction_quality"]["positioning_quality"] = 0.9 if has_valid_bbox else 0.3
        
        return structured_data
        
    except Exception as e:
        print(f"[WARN] Positioning extraction failed: {e}")
        # Return original data without positioning
        return structured_data

