"""
JSON schema validator and normalizer
"""
import json
import uuid
from typing import Dict, Any
from config import JSON_SCHEMA, QUESTION_SCHEMA


class JSONValidator:
    """Validate and normalize extracted JSON data"""
    
    def __init__(self):
        self.schema = JSON_SCHEMA
        self.question_schema = QUESTION_SCHEMA
    
    def validate_and_normalize(self, data: Dict[str, Any], document_name: str) -> Dict[str, Any]:
        """
        Validate extracted data against schema and normalize fields
        
        Args:
            data: Extracted data dictionary
            document_name: Original document name
            
        Returns:
            Validated and normalized dictionary
        """
        if not data:
            # Return minimal valid structure
            return self._create_empty_structure(document_name)
        
        # Ensure all required fields exist
        normalized = self._ensure_required_fields(data, document_name)
        
        # Validate and normalize questions
        normalized["questions"] = self._normalize_questions(
            normalized.get("questions", [])
        )
        
        # Update total_questions
        normalized["total_questions"] = str(len(normalized["questions"]))
        
        # Ensure docid exists
        if not normalized.get("docid") or normalized["docid"] == "string":
            normalized["docid"] = str(uuid.uuid4())
        
        return normalized
    
    def _ensure_required_fields(self, data: Dict, document_name: str) -> Dict:
        """Ensure all required fields exist with valid values"""
        normalized = {}
        
        # Required string fields
        string_fields = [
            "docid", "document_name", "institution_name", 
            "domain", "topic", "number_of_pages", "total_questions"
        ]
        
        for field in string_fields:
            value = data.get(field, "")
            
            # Convert to string and handle empty/invalid values
            if not value or value == "string" or value == "0":
                if field == "docid":
                    value = str(uuid.uuid4())
                elif field == "document_name":
                    value = document_name
                elif field == "institution_name":
                    value = "Unknown"
                elif field == "domain":
                    value = "General"
                elif field == "topic":
                    value = "Unknown"
                elif field == "number_of_pages":
                    value = "1"
                elif field == "total_questions":
                    value = "0"
            
            normalized[field] = str(value)
        
        # Questions array
        normalized["questions"] = data.get("questions", [])
        
        return normalized
    
    def _normalize_questions(self, questions: list) -> list:
        """Normalize question objects with granular schema"""
        if not questions:
            return []
        
        normalized_questions = []
        
        for idx, q in enumerate(questions, start=1):
            if not isinstance(q, dict):
                continue
            
            # Create normalized question with all granular fields
            normalized_q = {
                # Basic identification
                "question_number": self._safe_int(q.get("question_number", idx)),
                "question_type": str(q.get("question_type", q.get("type", "unknown"))),
                
                # Question content
                "stem_text": str(q.get("stem_text", q.get("text", ""))).strip(),
                "options": self._normalize_options(q.get("options")),
                "sub_questions": q.get("sub_questions") if q.get("sub_questions") else None,
                
                # Answers
                "gold_answer": str(q.get("gold_answer", q.get("answer", "Not provided"))),
                "gold_confidence": self._safe_float(q.get("gold_confidence", 0.5)),
                "answer_explanation": q.get("answer_explanation"),
                
                # Positioning
                "positioning": self._normalize_positioning(q.get("positioning", {})),
                
                # Content elements
                "formulas": self._normalize_array(q.get("formulas", [])),
                "visual_elements": self._normalize_array(q.get("visual_elements", [])),
                "tables": q.get("tables"),
                "code_snippets": q.get("code_snippets"),
                
                # Key terms and values
                "key_terms": self._normalize_key_terms(q.get("key_terms", [])),
                "numerical_values": q.get("numerical_values"),
                
                # Metadata
                "metadata": self._normalize_metadata(q.get("metadata", {})),
                
                # Confidence scores
                "confidence": self._safe_float(q.get("confidence", 0.5)),
                "extraction_quality": self._normalize_extraction_quality(
                    q.get("extraction_quality", {})
                ),
                
                # Original data
                "original_text": str(q.get("original_text", q.get("text", ""))).strip(),
                "page_number": self._safe_int(q.get("page_number", 1)),
                "source_page": str(q.get("source_page", f"page_{q.get('page_number', 1)}"))
            }
            
            # Only add if stem_text is not empty
            if normalized_q["stem_text"] and len(normalized_q["stem_text"]) > 3:
                normalized_questions.append(normalized_q)
        
        # Renumber questions sequentially
        for idx, q in enumerate(normalized_questions, start=1):
            q["question_number"] = idx
        
        return normalized_questions
    
    def _normalize_options(self, options) -> dict:
        """Normalize question options"""
        if not options or not isinstance(options, dict):
            return None
        
        # Ensure all options are strings
        normalized = {}
        for key, value in options.items():
            if value is not None:
                normalized[key] = str(value).strip()
        
        return normalized if normalized else None
    
    def _normalize_positioning(self, positioning: dict) -> dict:
        """Normalize positioning data"""
        return {
            "page": self._safe_int(positioning.get("page", 0)),
            "bbox": positioning.get("bbox", [0, 0, 0, 0]),
            "stem_bbox": positioning.get("stem_bbox", [0, 0, 0, 0]),
            "stem_spans": positioning.get("stem_spans", []),
            "option_bboxes": positioning.get("option_bboxes", {}),
            "extraction_order": self._safe_int(positioning.get("extraction_order", 0)),
            "method": str(positioning.get("method", "gpt4_vision"))
        }
    
    def _normalize_key_terms(self, key_terms: list) -> list:
        """Normalize key terms with positioning"""
        if not isinstance(key_terms, list):
            return []
        
        normalized = []
        for term in key_terms:
            if isinstance(term, dict):
                normalized_term = {
                    "term": str(term.get("term", "")),
                    "context": str(term.get("context", "stem")),
                    "alternatives": term.get("alternatives", []),
                    "importance": str(term.get("importance", "medium")),
                    "bbox": term.get("bbox", [0, 0, 0, 0]),
                    "span_ids": term.get("span_ids", []),
                    "char_start": self._safe_int(term.get("char_start", -1)),
                    "char_end": self._safe_int(term.get("char_end", -1))
                }
                if normalized_term["term"]:
                    normalized.append(normalized_term)
        
        return normalized
    
    def _normalize_metadata(self, metadata: dict) -> dict:
        """Normalize question metadata"""
        return {
            "subject_area": str(metadata.get("subject_area", "unknown")),
            "complexity": str(metadata.get("complexity", "medium")),
            "cognitive_level": metadata.get("cognitive_level"),
            "topic": str(metadata.get("topic", "unknown")),
            "subtopic": metadata.get("subtopic"),
            "has_images": bool(metadata.get("has_images", False)),
            "has_formulas": bool(metadata.get("has_formulas", False)),
            "has_code": bool(metadata.get("has_code", False)),
            "has_tables": bool(metadata.get("has_tables", False)),
            "estimated_time_seconds": self._safe_int_or_none(metadata.get("estimated_time_seconds")),
            "points": self._safe_int_or_none(metadata.get("points"))
        }
    
    def _normalize_extraction_quality(self, quality: dict) -> dict:
        """Normalize extraction quality scores"""
        return {
            "text_quality": self._safe_float(quality.get("text_quality", 0.5)),
            "positioning_quality": self._safe_float(quality.get("positioning_quality", 0.5)),
            "structure_confidence": self._safe_float(quality.get("structure_confidence", 0.5))
        }
    
    def _normalize_array(self, arr) -> list:
        """Normalize array, return empty list if not valid"""
        return arr if isinstance(arr, list) else []
    
    def _safe_int(self, value: Any) -> int:
        """Safely convert value to integer"""
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    
    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float"""
        try:
            f = float(value)
            # Clamp between 0 and 1 for confidence scores
            return max(0.0, min(1.0, f))
        except (ValueError, TypeError):
            return 0.5
    
    def _safe_int_or_none(self, value: Any) -> int:
        """Safely convert value to integer or return None"""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    
    def _create_empty_structure(self, document_name: str) -> Dict:
        """Create minimal valid structure when extraction fails"""
        return {
            "docid": str(uuid.uuid4()),
            "document_name": document_name,
            "institution_name": "Unknown",
            "domain": "General",
            "topic": "Unknown",
            "number_of_pages": "1",
            "total_questions": "0",
            "questions": []
        }
    
    def save_to_file(self, data: Dict, output_path: str) -> bool:
        """
        Save validated JSON to file
        
        Args:
            data: Validated data dictionary
            output_path: Path to save JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving JSON file: {e}")
            return False

