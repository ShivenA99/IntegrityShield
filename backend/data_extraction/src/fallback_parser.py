"""
Fallback heuristic/regex-based parser for question extraction
"""
import re
import uuid
from typing import Dict, List
from config import QUESTION_PATTERNS, QUESTION_TYPE_KEYWORDS


class FallbackParser:
    """Deterministic fallback parser using regex and heuristics"""
    
    def __init__(self):
        self.question_patterns = [re.compile(p, re.MULTILINE | re.IGNORECASE) 
                                 for p in QUESTION_PATTERNS]
    
    def extract(self, text_data: Dict, document_name: str) -> Dict:
        """
        Extract questions using heuristic parsing
        
        Args:
            text_data: Dictionary containing text and page information
            document_name: Name of the document
            
        Returns:
            Structured dictionary with questions
        """
        print("Using fallback parser (regex/heuristic)...")
        
        full_text = text_data.get("text", "")
        pages = text_data.get("pages", [])
        number_of_pages = text_data.get("number_of_pages", 1)
        
        # Extract metadata
        metadata = self._extract_metadata(full_text, document_name)
        
        # Extract questions
        questions = self._extract_questions(pages, full_text)
        
        # Build final structure
        result = {
            "docid": str(uuid.uuid4()),
            "document_name": metadata.get("document_name", document_name),
            "institution_name": metadata.get("institution_name", "Unknown"),
            "domain": metadata.get("domain", "General"),
            "topic": metadata.get("topic", "Unknown"),
            "number_of_pages": str(number_of_pages),
            "total_questions": str(len(questions)),
            "questions": questions
        }
        
        print(f"Fallback parser extracted {len(questions)} questions")
        return result
    
    def _extract_metadata(self, text: str, document_name: str) -> Dict:
        """Extract document metadata using pattern matching"""
        metadata = {
            "document_name": document_name,
            "institution_name": "Unknown",
            "domain": "General",
            "topic": "Unknown"
        }
        
        # Look for institution name in first 500 characters
        first_part = text[:500]
        
        # Common patterns for institution names
        institution_patterns = [
            r"(?:University|College|Institute|School)\s+(?:of\s+)?([A-Z][A-Za-z\s]+)",
            r"([A-Z][A-Za-z]+\s+(?:University|College|Institute|School))",
        ]
        
        for pattern in institution_patterns:
            match = re.search(pattern, first_part)
            if match:
                metadata["institution_name"] = match.group(0).strip()
                break
        
        # Detect domain from keywords
        domain_keywords = {
            "Physics": ["physics", "mechanics", "thermodynamics", "quantum"],
            "Mathematics": ["mathematics", "math", "calculus", "algebra", "geometry"],
            "Chemistry": ["chemistry", "chemical", "organic", "inorganic"],
            "Biology": ["biology", "biological", "cell", "genetics"],
            "Computer Science": ["computer", "programming", "algorithm", "software"],
        }
        
        text_lower = text.lower()
        for domain, keywords in domain_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                metadata["domain"] = domain
                break
        
        # Try to extract topic from title/heading
        lines = text.split('\n')[:20]
        for line in lines:
            line = line.strip()
            if line and len(line) < 100 and not line[0].isdigit():
                # Might be a title
                if any(keyword in line.lower() for keywords in domain_keywords.values() for keyword in keywords):
                    metadata["topic"] = line
                    break
        
        return metadata
    
    def _extract_questions(self, pages: List[Dict], full_text: str) -> List[Dict]:
        """Extract individual questions from text"""
        questions = []
        
        if pages:
            # Process page by page
            for page_data in pages:
                page_num = page_data.get("page_number", 1)
                page_text = page_data.get("text", "")
                page_questions = self._parse_questions_from_text(page_text, page_num)
                questions.extend(page_questions)
        else:
            # Process full text
            questions = self._parse_questions_from_text(full_text, 1)
        
        # Renumber questions sequentially
        for idx, q in enumerate(questions, start=1):
            q["question_number"] = idx
        
        return questions
    
    def _parse_questions_from_text(self, text: str, page_number: int) -> List[Dict]:
        """Parse questions from a text block"""
        questions = []
        
        # Split text into potential question blocks
        # Look for patterns like "1.", "Q1", "Question 1", etc.
        question_splits = re.split(
            r'\n(?=(?:\d+\.|Q\.?\d+|Question\s+\d+))',
            text
        )
        
        for block in question_splits:
            block = block.strip()
            if not block or len(block) < 10:
                continue
            
            # Check if this looks like a question
            if self._is_likely_question(block):
                question = self._parse_question_block(block, page_number)
                if question:
                    questions.append(question)
        
        return questions
    
    def _is_likely_question(self, text: str) -> bool:
        """Heuristic to determine if text block is a question"""
        # Check for question indicators
        indicators = [
            r'^\d+\.',  # Starts with number
            r'^Q\.?\d+',  # Starts with Q1, Q.1, etc.
            r'Question\s+\d+',  # "Question 1"
            r'\?',  # Contains question mark
            r'\b(?:what|where|when|why|how|which)\b',  # Question words
            r'\b(?:choose|select|identify|calculate|explain|describe)\b',  # Instruction words
        ]
        
        text_lower = text.lower()
        for pattern in indicators:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _parse_question_block(self, block: str, page_number: int) -> Dict:
        """Parse a single question block"""
        question = {
            "question_number": 0,  # Will be set later
            "type": "Unknown",
            "text": "",
            "answer": "Not provided",
            "page_number": str(page_number),
            "figure": "no"
        }
        
        # Extract question number from start
        num_match = re.match(r'^(?:Q\.?\s*)?(\d+)[\.\):]?\s*', block)
        if num_match:
            question["question_number"] = int(num_match.group(1))
            # Remove the number from text
            block = block[num_match.end():]
        
        # Determine question type
        question["type"] = self._determine_question_type(block)
        
        # Check for figures/images
        if any(keyword in block.lower() for keyword in ["figure", "diagram", "image", "graph", "chart", "shown above", "shown below"]):
            question["figure"] = "yes"
        
        # Extract answer if present
        answer_patterns = [
            r'(?:Answer|Ans|Solution)[:.]?\s*([^\n]+)',
            r'Correct answer[:.]?\s*([^\n]+)',
        ]
        
        for pattern in answer_patterns:
            match = re.search(pattern, block, re.IGNORECASE)
            if match:
                question["answer"] = match.group(1).strip()
                # Remove answer from question text
                block = block[:match.start()].strip()
                break
        
        # Clean up text
        question["text"] = block.strip()
        
        # Only return if we have valid text
        if len(question["text"]) < 5:
            return None
        
        return question
    
    def _determine_question_type(self, text: str) -> str:
        """Determine question type from text content"""
        text_lower = text.lower()
        
        for q_type, keywords in QUESTION_TYPE_KEYWORDS.items():
            if any(keyword.lower() in text_lower for keyword in keywords):
                return q_type
        
        # Default type based on length and structure
        if len(text) < 200:
            return "Short Answer"
        else:
            return "Essay"

