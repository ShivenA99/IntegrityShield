"""
Configuration file for the Question Extraction Pipeline
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# API Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o"  # Latest multimodal model (GPT-4 Omni)
OPENAI_MAX_TOKENS = 16000  # Increased for granular schema with positioning data
OPENAI_TEMPERATURE = 0.1  # Low temperature for deterministic outputs

# Mistral API Configuration
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_MODEL = "pixtral-12b-2409"  # Mistral's vision model (Pixtral)
MISTRAL_MAX_TOKENS = 4096
MISTRAL_TEMPERATURE = 0.0  # Deterministic for OCR

# Chunking Configuration (v4.1.2)
AUTO_CHUNK_THRESHOLD = 6  # Trigger chunking at 6+ questions (safe threshold)
QUESTIONS_PER_CHUNK = 2   # Process 2 questions per chunk (optimized for speed and parallelization)

# File Paths
BASE_DIR = Path(__file__).parent
DATASET_DIR = BASE_DIR / "Dataset"
OUTPUT_DIR = BASE_DIR / "Output"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# Supported file formats
SUPPORTED_FORMATS = [".pdf", ".docx", ".txt"]

# JSON Schema Template
JSON_SCHEMA = {
    "docid": "string",
    "document_name": "string",
    "institution_name": "string",
    "domain": "string",
    "topic": "string",
    "number_of_pages": "string",
    "total_questions": "string",
    "questions": []
}

QUESTION_SCHEMA = {
    "question_number": 0,
    "question_type": "string",
    "stem_text": "string",
    "options": {},
    "sub_questions": None,
    "gold_answer": "string",
    "gold_confidence": 0.0,
    "answer_explanation": None,
    "positioning": {
        "page": 0,
        "bbox": [],
        "stem_bbox": [],
        "stem_spans": [],
        "option_bboxes": {},
        "extraction_order": 0,
        "method": "string"
    },
    "formulas": [],
    "visual_elements": [],
    "tables": None,
    "code_snippets": None,
    "key_terms": [],
    "numerical_values": None,
    "metadata": {
        "subject_area": "string",
        "complexity": "string",
        "cognitive_level": None,
        "topic": "string",
        "subtopic": None,
        "has_images": False,
        "has_formulas": False,
        "has_code": False,
        "has_tables": False,
        "estimated_time_seconds": None,
        "points": None
    },
    "confidence": 0.0,
    "extraction_quality": {
        "text_quality": 0.0,
        "positioning_quality": 0.0,
        "structure_confidence": 0.0
    },
    "original_text": "string",
    "page_number": 0,
    "source_page": "string"
}

# OpenAI System Prompt - Enhanced for Granular Extraction
EXTRACTION_PROMPT = """You are an expert document parser with multimodal capabilities specialized in granular question extraction for academic integrity analysis.

I will provide you with:
1. The FULL TEXT extracted from a question paper document
2. Any EMBEDDED IMAGES (diagrams, figures, charts) referenced in the questions

Your task is to analyze both the text and images to extract ALL questions with MAXIMUM GRANULARITY and return them in a highly structured JSON format.

For each question, extract the following:

## QUESTION STRUCTURE:
1. question_number: Sequential number (1, 2, 3...)
2. question_type: Classify as one of:
   - "mcq_single" (single correct answer)
   - "mcq_multiple" (multiple correct answers)
   - "true_false" (true/false question)
   - "short_answer" (brief written response)
   - "essay" (extended written response)
   - "numerical" (numerical answer required)
   - "fill_blank" (fill in the blank)
   - "matching" (match items)
   - "calculation" (mathematical calculation)
   - "unknown" (if cannot determine)

3. stem_text: The ACTUAL QUESTION TEXT ONLY (without options)
4. options: For MCQ, create object with keys A, B, C, D, etc. and option text as values. Use null for non-MCQ.
5. sub_questions: Array of sub-parts if multi-part question, null otherwise. Format:
   [{"part": "a", "text": "...", "points": 5}]

## ANSWERS:
6. gold_answer: The correct answer (e.g., "C", "True", or actual answer text). "Not provided" if not given.
7. gold_confidence: Your confidence in the answer (0.0 to 1.0). Use 0.5 if answer not provided.
8. answer_explanation: Explanation of why the answer is correct, if provided. null otherwise.

## CONTENT ELEMENTS:
9. formulas: Array of mathematical formulas in the question. For each formula:
   {
     "text": "Plain text representation",
     "latex": "LaTeX notation if you can convert it",
     "position": "stem" or "option_A", "option_B", etc.,
     "description": "Brief description of the formula"
   }
   Use [] if no formulas.

10. visual_elements: Array of diagrams, graphs, tables, images. For each:
    {
      "type": "diagram" | "graph" | "table" | "image" | "chart",
      "reference": "Figure 1" or how it's referenced,
      "description": "Detailed description of what the visual shows",
      "is_embedded": true/false (if actual image vs just referenced)
    }
    Use [] if no visual elements.

11. tables: Array of tables in the question. For each:
    {
      "data": [["row1col1", "row1col2"], ["row2col1", "row2col2"]],
      "headers": ["Header1", "Header2"],
      "position": "stem" or which option,
      "description": "What the table shows"
    }
    Use null if no tables.

12. code_snippets: Array of code blocks. For each:
    {
      "language": "python" | "java" | "c++" | "javascript" | "pseudocode" | etc.,
      "code": "actual code text",
      "line_numbers": true/false,
      "position": "stem" or which option
    }
    Use null if no code.

## KEY TERMS (for substitution analysis):
13. key_terms: Array of important terms that could be substituted. For each:
    {
      "term": "worst-case",
      "context": "stem" or "option_A", etc.,
      "alternatives": ["average-case", "best-case"],  // plausible alternatives
      "importance": "critical" | "high" | "medium" | "low"
    }
    Extract 3-5 key terms per question.

14. numerical_values: Array of numerical values in the question. For each:
    {
      "value": "9.8",
      "unit": "m/s²",
      "context": "stem" or which option,
      "role": "given_data" | "expected_answer" | "distractor"
    }
    Use null if no numerical values.

## METADATA:
15. metadata: Object with:
    {
      "subject_area": "physics" | "mathematics" | "computer_science" | "chemistry" | "biology" | "engineering" | etc.,
      "complexity": "easy" | "medium" | "hard" (assess difficulty),
      "cognitive_level": "remember" | "understand" | "apply" | "analyze" | "evaluate" | "create" (Bloom's taxonomy),
      "topic": "Main topic (e.g., 'algorithms')",
      "subtopic": "Specific subtopic (e.g., 'complexity_analysis')",
      "has_images": true/false,
      "has_formulas": true/false,
      "has_code": true/false,
      "has_tables": true/false,
      "estimated_time_seconds": estimated time to solve (integer or null),
      "points": point value if provided (integer or null)
    }

16. confidence: Overall confidence in extraction quality (0.0 to 1.0)

17. extraction_quality: Object with:
    {
      "text_quality": 0.0-1.0 (how clean is the text),
      "structure_confidence": 0.0-1.0 (how confident in question structure)
    }

18. original_text: The COMPLETE original text of the entire question including all options
19. page_number: Page number where question starts (integer)
20. source_page: "page_1", "page_2", etc.

## DOCUMENT METADATA (at root level):
- document_name: Title of the document
- institution_name: Name of the institution/organization
- domain: Subject domain (Physics, Mathematics, Computer Science, etc.)
- topic: Specific topic within the domain
- number_of_pages: Total pages in the document (string)
- total_questions: Total number of questions (string)

## CRITICAL INSTRUCTIONS:
1. Extract EVERY field for EVERY question
2. Use null (not empty string "") for non-applicable fields
3. Be thorough in identifying key_terms - these are crucial for substitution attacks
4. For formulas, try to convert to LaTeX notation if possible
5. Separate question stem from options clearly
6. Provide detailed descriptions for visual elements
7. Assess complexity and cognitive level accurately
8. Return ONLY valid JSON, no markdown formatting or additional text
9. All numerical values should be strings in JSON (e.g., "1", "2", not 1, 2)

## MULTIPLE QUESTION SECTIONS:
Documents may contain MULTIPLE question sections (e.g., Multiple Choice, True/False, Short Answer, Essay).
- Each section may RESTART numbering (e.g., "1. True or False..." appears after "8. Multiple Choice...")
- Extract ALL questions from ALL sections - DO NOT stop after the first section
- If you see "Multiple Choice (16 marks)" with questions numbered 1-8, and "True / False (24 marks)" with questions numbered 1-12, extract ALL 20 questions
- True/False questions should be classified as question_type: "true_false"
- Maintain sequential numbering across all sections: if MCQ has 1-8 and True/False has 1-12, number them as 1-8 and 9-20 respectively
- Example: A document with "Multiple Choice" section (questions 1-8) followed by "True/False" section (questions 1-12) should result in 20 total questions extracted

Return the complete structured JSON following this exact schema."""

# Mistral OCR Prompt
MISTRAL_OCR_PROMPT = """Extract ALL text from this document page image exactly as it appears.

Your task:
1. Read all visible text in the correct reading order
2. Preserve formatting, spacing, and structure
3. Include question numbers, options, and any text in diagrams
4. Maintain the original layout as much as possible
5. Extract any mathematical equations or formulas accurately

Return ONLY the extracted text, no additional commentary."""

# Fallback Parser Configuration
QUESTION_PATTERNS = [
    r"(?:Question|Q\.?|^\d+\.)\s*(\d+)",
    r"^\d+\.\s+",
    r"^Q\d+[:\.]?\s+",
]

QUESTION_TYPE_KEYWORDS = {
    "Multiple Choice": ["A)", "B)", "C)", "D)", "(a)", "(b)", "(c)", "(d)"],
    "True/False": ["True or False", "T/F", "True/False"],
    "Short Answer": ["short answer", "briefly explain", "describe"],
    "Essay": ["essay", "discuss in detail", "elaborate"],
    "Fill in the Blank": ["fill in", "______", "blank"],
}

# =============================================================================
# LaTeX Reconstruction Configuration (v5.0.0)
# =============================================================================

# Enable/disable LaTeX reconstruction features
ENABLE_LATEX_RECONSTRUCTION = True  # Default: enabled for FairTestAI pipeline integration

# LaTeX generation settings
LATEX_INCLUDE_IMAGES = True          # Extract and include images in LaTeX
LATEX_COMPILE_PDF = False            # Compile LaTeX to PDF (requires pdflatex/xelatex)
LATEX_ENGINE = "pdflatex"            # LaTeX engine: "pdflatex" or "xelatex" (for Unicode)
LATEX_GENERATE_MARKDOWN = True       # Generate markdown file
LATEX_GENERATE_STRUCTURED_JSON = True # Generate simplified structured JSON

# LaTeX output settings
LATEX_KEEP_INTERMEDIATE_FILES = False # Keep .aux, .log files after compilation
LATEX_DPI = 300                      # DPI for image extraction (higher = better quality)

# =============================================================================
# Smart LaTeX Reconstruction (AI-First, No Regex!)
# =============================================================================

# Smart reconstruction settings
SMART_LATEX_PDF_DPI = 200            # DPI for PDF → image conversion for GPT-4 Vision
SMART_LATEX_MAX_PAGES = 10           # Max pages to send to GPT-4 Vision (token limits)

# Quality: 90-95% layout accuracy with automatic spacing fixes
# Method: Pure AI-first approach (GPT-4 Vision analyzes layout visually)

