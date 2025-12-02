"""
Main pipeline orchestrator for question extraction
Enhanced with Mistral OCR integration for scanned documents
"""
from pathlib import Path
from typing import Optional, Dict
import json
import time
from datetime import datetime

from .document_readers import get_reader, is_text_quality_good, compare_text_quality
from .openai_extractor import OpenAIExtractor
from .mistral_ocr import MistralOCRExtractor
from .fallback_parser import FallbackParser
from .json_validator import JSONValidator
from .smart_latex_reconstructor import SmartLaTeXReconstructor
from config import (
    OUTPUT_DIR, SUPPORTED_FORMATS, AUTO_CHUNK_THRESHOLD, QUESTIONS_PER_CHUNK,
    ENABLE_LATEX_RECONSTRUCTION, LATEX_INCLUDE_IMAGES, LATEX_COMPILE_PDF
)


class QuestionExtractionPipeline:
    """
    Hybrid pipeline for extracting questions from PDF/DOCX/TXT documents
    Combines PyMuPDF, Mistral OCR, and GPT-4 Vision for optimal results
    
    Architecture:
    1. PyMuPDF: Text extraction (text-based PDFs)
    2. Mistral OCR: Text extraction (scanned PDFs, poor quality)
    3. PyMuPDF: Image extraction (always)
    4. GPT-4 Vision: Final question extraction (always)
    """
    
    def __init__(
        self, 
        use_openai: bool = True, 
        use_mistral: bool = True,
        openai_api_key: str = None,
        enable_latex: bool = False,
        latex_include_images: bool = True,
        latex_compile_pdf: bool = False
    ):
        """
        Initialize pipeline
        
        Args:
            use_openai: Whether to use OpenAI extraction (requires API key)
            use_mistral: Whether to use Mistral OCR for scanned docs (requires API key in .env)
            openai_api_key: OpenAI API key (optional, can use env var)
            enable_latex: Whether to enable LaTeX reconstruction (default: False)
            latex_include_images: Whether to extract and include images in LaTeX (default: True)
            latex_compile_pdf: Whether to compile LaTeX to PDF (default: False)
        
        Note: Mistral API key is always loaded from .env file for security
        """
        self.use_openai = use_openai
        self.use_mistral = use_mistral
        self.enable_latex = enable_latex
        self.latex_include_images = latex_include_images
        self.latex_compile_pdf = latex_compile_pdf
        self.openai_extractor = None
        self.mistral_ocr = None
        self.latex_reconstructor = None
        self.fallback_parser = FallbackParser()
        self.validator = JSONValidator()
        
        # Track initialization timings for logging
        self.initialization_timings = []
        
        # Initialize OpenAI extractor
        if use_openai:
            try:
                init_start = time.time()
                self.openai_extractor = OpenAIExtractor(api_key=openai_api_key)
                init_end = time.time()
                init_duration = init_end - init_start
                self.initialization_timings.append({
                    "step": "openai_extractor_initialization",
                    "start_time": datetime.fromtimestamp(init_start).isoformat(),
                    "end_time": datetime.fromtimestamp(init_end).isoformat(),
                    "duration_seconds": round(init_duration, 3),
                    "duration_formatted": self._format_duration(init_duration),
                    "success": True
                })
                print("[OK] OpenAI extractor initialized")
            except ValueError as e:
                self.initialization_timings.append({
                    "step": "openai_extractor_initialization",
                    "success": False,
                    "error": str(e)
                })
                print(f"[WARN] OpenAI extractor not available: {e}")
                print("[WARN] Will use fallback parser only")
                self.use_openai = False
        
        # Initialize Mistral OCR (API key loaded from .env only)
        if use_mistral:
            try:
                init_start = time.time()
                self.mistral_ocr = MistralOCRExtractor()
                init_end = time.time()
                init_duration = init_end - init_start
                self.initialization_timings.append({
                    "step": "mistral_ocr_initialization",
                    "start_time": datetime.fromtimestamp(init_start).isoformat(),
                    "end_time": datetime.fromtimestamp(init_end).isoformat(),
                    "duration_seconds": round(init_duration, 3),
                    "duration_formatted": self._format_duration(init_duration),
                    "success": True
                })
                print("[OK] Mistral OCR initialized (API key from .env)")
            except ValueError as e:
                self.initialization_timings.append({
                    "step": "mistral_ocr_initialization",
                    "success": False,
                    "error": str(e)
                })
                print(f"[WARN] Mistral OCR not available: {e}")
                print("[WARN] Will rely on PyMuPDF text extraction only")
                self.use_mistral = False
        
        # Initialize LaTeX reconstructor (optional)
        if enable_latex:
            try:
                init_start = time.time()
                self.latex_reconstructor = SmartLaTeXReconstructor()
                init_end = time.time()
                init_duration = init_end - init_start
                self.initialization_timings.append({
                    "step": "latex_reconstructor_initialization",
                    "start_time": datetime.fromtimestamp(init_start).isoformat(),
                    "end_time": datetime.fromtimestamp(init_end).isoformat(),
                    "duration_seconds": round(init_duration, 3),
                    "duration_formatted": self._format_duration(init_duration),
                    "success": True
                })
                print("[OK] Smart LaTeX reconstructor initialized (AI-first, 90-95% quality)")
            except ValueError as e:
                self.initialization_timings.append({
                    "step": "latex_reconstructor_initialization",
                    "success": False,
                    "error": str(e)
                })
                print(f"[WARN] LaTeX reconstructor not available: {e}")
                print("[WARN] LaTeX reconstruction will be disabled")
                self.enable_latex = False
    
    def _format_duration(self, seconds: float) -> str:
        """
        Format duration in a human-readable format.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string (e.g., "2m 30.5s", "45.2s")
        """
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.2f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hours}h {minutes}m {secs:.2f}s"
    
    def _estimate_question_count(self, text: str) -> int:
        """
        Estimate the number of questions in the document text
        Enhanced to detect sub-questions (e.g., 1.a, i), (a), etc.)
        
        Args:
            text: Full document text
            
        Returns:
            Estimated number of questions (including sub-questions)
        """
        import re
        
        # Detect ALL question-like patterns (main + sub-questions)
        all_patterns = [
            # Main questions
            r'(?:^|\n)(?:Question|Q\.?)\s*\d+',     # "Question 1", "Q1"
            r'(?:^|\n)\d+\.\s+[A-Z]',                # "1. What", "2. Explain"
            r'(?:^|\n)\d+\)\s+[A-Z]',                # "1) What", "2) Explain"
            # Sub-questions
            r'(?:^|\n)\d+\.[a-z]\)',                 # "1.a)", "2.b)"
            r'(?:^|\n)\d+\.[a-z]\s',                 # "1.a ", "2.b "
            r'(?:^|\n)[a-z]\)\s+',                   # "a) ", "b) "
            r'(?:^|\n)\([a-z]\)\s+',                 # "(a) ", "(b) "
            r'(?:^|\n)[ivx]+\)\s+',                  # "i) ", "ii) ", "iii) "
            r'(?:^|\n)\([ivx]+\)\s+',                # "(i) ", "(ii) "
        ]
        
        # Collect ALL matches with positions to avoid double-counting
        match_positions = set()
        for pattern in all_patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                # Store position to deduplicate overlapping matches
                match_positions.add(match.start())
        
        count = len(match_positions)
        
        # Return count, or estimate based on text length if no patterns found
        if count > 0:
            return count
        else:
            # Fallback: estimate ~500 chars per question
            return max(1, len(text) // 500)
    
    def process_document(self, file_path: str, output_path: str = None) -> Dict:
        """
        Process a single document through the hybrid pipeline
        
        Pipeline Flow:
        1. Try PyMuPDF text extraction
        2. Check text quality
        3. If poor quality: Use Mistral OCR
        4. Extract embedded images (PyMuPDF)
        5. Send to GPT-4 Vision for question extraction
        
        Args:
            file_path: Path to input document (PDF/DOCX/TXT)
            output_path: Optional custom output path for JSON
            
        Returns:
            Extracted and validated data dictionary
        """
        file_path = Path(file_path)
        
        # Validate file
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if file_path.suffix.lower() not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {file_path.suffix}. Supported: {SUPPORTED_FORMATS}")
        
        print(f"\n{'='*60}")
        print(f"Processing: {file_path.name}")
        print(f"{'='*60}")
        
        # Step 1: Try PyMuPDF text extraction first
        print("\n[1/5] Extracting text with PyMuPDF...")
        reader = get_reader(str(file_path))
        text_data = reader.read_text()
        print(f"[OK] Extracted {len(text_data['text'])} characters from {text_data['number_of_pages']} page(s)")
        
        # Step 2: Check text quality and decide on extraction method
        text_source = "PyMuPDF"
        final_text_data = text_data
        quality_is_poor = False
        text_quality_good = False  # Track text quality for LaTeX reconstruction
        
        print("\n[2/5] Analyzing text quality...")
        if is_text_quality_good(text_data['text']):
            print("[OK] Text quality is good - using PyMuPDF extraction")
            text_source = "PyMuPDF"
            text_quality_good = True
        else:
            print("[WARN] Text quality is poor - checking for Mistral OCR...")
            quality_is_poor = True
            text_quality_good = False
            
            # Use Mistral OCR if available
            if self.use_mistral and self.mistral_ocr and file_path.suffix.lower() == ".pdf":
                print("[INFO] Using Mistral OCR for better text extraction...")
                
                try:
                    # Render pages as images for OCR
                    page_images = reader.render_pages_for_ocr(dpi=300)
                    print(f"[OK] Rendered {len(page_images)} page(s) for OCR")
                    
                    # Extract text with Mistral OCR
                    ocr_result = self.mistral_ocr.extract_text_from_document(page_images)
                    
                    # Smart comparison using multiple quality metrics
                    winner, comparison = compare_text_quality(
                        text_data['text'], 
                        ocr_result['text'],
                        was_quality_poor=quality_is_poor
                    )
                    
                    # Log detailed comparison
                    print(f"\n[COMPARISON] Mistral OCR vs PyMuPDF:")
                    pymupdf_m = comparison['pymupdf']
                    mistral_m = comparison['mistral']
                    print(f"  PyMuPDF:     {pymupdf_m['char_count']:,} chars | {pymupdf_m['word_count']:,} words | "
                          f"{pymupdf_m['alphanumeric_ratio']*100:.0f}% alphanumeric | "
                          f"avg word: {pymupdf_m['avg_word_length']:.1f} chars")
                    print(f"  Mistral OCR: {mistral_m['char_count']:,} chars | {mistral_m['word_count']:,} words | "
                          f"{mistral_m['alphanumeric_ratio']*100:.0f}% alphanumeric | "
                          f"avg word: {mistral_m['avg_word_length']:.1f} chars")
                    
                    # Use the winner
                    if winner == "Mistral OCR":
                        final_text_data = ocr_result
                        text_source = "Mistral OCR"
                        # Update text quality based on winner
                        text_quality_good = is_text_quality_good(ocr_result['text'])
                        print(f"[DECISION] Using Mistral OCR - {comparison['reason']}")
                    else:
                        text_source = "PyMuPDF"
                        # PyMuPDF won, so quality is good (that's why we didn't use OCR)
                        text_quality_good = True
                        print(f"[DECISION] Using PyMuPDF - {comparison['reason']}")
                        
                except Exception as e:
                    print(f"[ERROR] Mistral OCR failed: {e}")
                    print("[WARN] Falling back to PyMuPDF text")
            else:
                print("[WARN] Mistral OCR not available - using PyMuPDF text anyway")
        
        # Step 3: Extract embedded images (always use PyMuPDF for this)
        print(f"\n[3/5] Extracting embedded images...")
        embedded_images = []
        if file_path.suffix.lower() == ".pdf" and text_data.get("has_images"):
            try:
                embedded_images = reader.read_images()
                if embedded_images:
                    print(f"[OK] Extracted {len(embedded_images)} embedded image(s) (diagrams/figures)")
                else:
                    print("[INFO] No embedded images found")
            except Exception as e:
                print(f"[WARN] Image extraction failed: {e}")
        else:
            print("[INFO] No embedded images to extract")
        
        # Step 4: Use GPT-4 Vision for final extraction with positioning
        extracted_data = None
        used_api = False
        chunking_timing = None  # Track chunking/extraction timing
        
        if self.use_openai and self.openai_extractor:
            print(f"\n[4/5] Sending to GPT-4 Vision with positioning extraction (text from: {text_source})...")
            
            try:
                # Pass PDF path for positioning extraction
                pdf_path_str = str(file_path) if file_path.suffix.lower() == ".pdf" else None
                
                # Decide whether to use chunking
                # Try LLM-based count first (more accurate), fallback to regex
                estimated_questions = None
                
                # Quick metadata call to get accurate question count
                try:
                    metadata = self.openai_extractor._extract_document_metadata(
                        final_text_data["text"], 
                        file_path.stem
                    )
                    estimated_questions = metadata.get("estimated_questions")
                    if estimated_questions:
                        print(f"[INFO] LLM-based count: ~{estimated_questions} questions detected")
                except Exception as e:
                    print(f"[WARN] LLM count failed: {e}, using regex fallback")
                
                # Fallback to regex if LLM count failed
                if estimated_questions is None:
                    estimated_questions = self._estimate_question_count(final_text_data["text"])
                    print(f"[INFO] Regex-based count: ~{estimated_questions} questions detected")
                
                use_chunking = estimated_questions >= AUTO_CHUNK_THRESHOLD  # Use chunking based on config (default: 6)
                
                if use_chunking:
                    print(f"[INFO] Document has ~{estimated_questions} questions - using chunked extraction")
                    chunking_start = time.time()
                    extracted_data = self.openai_extractor.extract_with_chunking(
                        text=final_text_data["text"],
                        images=embedded_images,
                        document_name=file_path.stem,
                        metadata={
                            **final_text_data.get("metadata", {}),
                            "text_extraction_method": text_source
                        },
                        pdf_path=pdf_path_str,
                        questions_per_chunk=QUESTIONS_PER_CHUNK
                    )
                    chunking_end = time.time()
                    chunking_duration = chunking_end - chunking_start
                    chunking_timing = {
                        "step": "chunking_extraction",
                        "start_time": datetime.fromtimestamp(chunking_start).isoformat(),
                        "end_time": datetime.fromtimestamp(chunking_end).isoformat(),
                        "duration_seconds": round(chunking_duration, 3),
                        "duration_formatted": self._format_duration(chunking_duration),
                        "estimated_questions": estimated_questions,
                        "questions_per_chunk": QUESTIONS_PER_CHUNK,
                        "method": "chunked"
                    }
                else:
                    print(f"[INFO] Document has ~{estimated_questions} questions - using single extraction")
                    single_start = time.time()
                    # Use hybrid extraction (text + embedded images + positioning)
                    extracted_data = self.openai_extractor.extract_from_text_and_images(
                        text=final_text_data["text"],
                        images=embedded_images,
                        document_name=file_path.stem,
                        metadata={
                            **final_text_data.get("metadata", {}),
                            "text_extraction_method": text_source
                        },
                        pdf_path=pdf_path_str
                    )
                    single_end = time.time()
                    single_duration = single_end - single_start
                    chunking_timing = {
                        "step": "single_extraction",
                        "start_time": datetime.fromtimestamp(single_start).isoformat(),
                        "end_time": datetime.fromtimestamp(single_end).isoformat(),
                        "duration_seconds": round(single_duration, 3),
                        "duration_formatted": self._format_duration(single_duration),
                        "estimated_questions": estimated_questions,
                        "method": "single"
                    }
                
                if extracted_data and extracted_data.get("questions"):
                    used_api = True
                    num_questions = len(extracted_data.get('questions', []))
                    print(f"[OK] GPT-4 Vision extracted {num_questions} questions with granular data")
                    
                    # Count questions with positioning data
                    positioned_count = sum(
                        1 for q in extracted_data.get('questions', [])
                        if q.get('positioning', {}).get('bbox', [0,0,0,0]) != [0,0,0,0]
                    )
                    if positioned_count > 0:
                        print(f"[OK] {positioned_count}/{num_questions} questions have positioning data")
                
            except Exception as e:
                print(f"[ERROR] GPT-4 Vision extraction failed: {e}")
        else:
            print("\n[4/5] Skipping GPT-4 Vision (not available)")
        
        # Step 5: Use fallback parser if GPT-4 failed
        if not extracted_data or not extracted_data.get("questions"):
            print("\n[INFO] Using fallback regex parser...")
            extracted_data = self.fallback_parser.extract(final_text_data, file_path.stem)
            used_api = False
        else:
            print("[INFO] GPT-4 extraction successful, skipping fallback")
        
        # Step 6: Validate and normalize
        print("\n[5/5] Validating and normalizing output...")
        validated_data = self.validator.validate_and_normalize(
            extracted_data, 
            file_path.stem
        )
        
        print(f"[OK] Validation complete")
        print(f"  - Document: {validated_data['document_name']}")
        print(f"  - Institution: {validated_data['institution_name']}")
        print(f"  - Domain: {validated_data['domain']}")
        print(f"  - Total Questions: {validated_data['total_questions']}")
        print(f"  - Text Source: {text_source}")
        
        # Determine method for display
        if used_api:
            method = f"API ({text_source})"
        else:
            method = "No-API"
        
        # Step 7: Save output
        if not output_path:
            # Determine subfolder based on whether API was used
            if used_api:
                output_subfolder = OUTPUT_DIR / "output_api"
            else:
                output_subfolder = OUTPUT_DIR / "output_noapi"
            
            output_subfolder.mkdir(parents=True, exist_ok=True)
            output_path = output_subfolder / f"{file_path.stem}_extracted.json"
        
        success = self.validator.save_to_file(validated_data, str(output_path))
        
        if success:
            print(f"\n[OK] Output saved to: {output_path} [{method}]")
        else:
            print(f"\n[ERROR] Failed to save output")
        
        # Step 8: LaTeX Reconstruction (Optional)
        if self.enable_latex and self.latex_reconstructor and file_path.suffix.lower() == ".pdf":
            print(f"\n{'='*60}")
            print("LATEX RECONSTRUCTION (Optional)")
            print(f"{'='*60}")
            
            try:
                # Determine output directory for LaTeX files
                latex_output_dir = OUTPUT_DIR / "latex_reconstruction"
                latex_output_dir.mkdir(parents=True, exist_ok=True)
                
                # Process document for LaTeX reconstruction
                # Smart AI-first reconstruction
                # Pass initialization and chunking timings to be included in timing log
                # Pass text quality info to skip unnecessary OCR
                latex_results = self.latex_reconstructor.reconstruct_pdf_to_latex(
                    pdf_path=str(file_path),
                    output_dir=str(latex_output_dir),
                    include_images=self.latex_include_images,
                    compile_pdf=self.latex_compile_pdf,
                    external_timings={
                        "initialization": self.initialization_timings,
                        "chunking": chunking_timing
                    } if chunking_timing else {"initialization": self.initialization_timings},
                    use_mistral_ocr=False,  # Default to False for speed
                    skip_ocr_if_text_good=True,  # Skip OCR if text quality is good
                    text_quality_good=text_quality_good  # Pass quality status from main pipeline
                )
                
                # Log all generated files
                print(f"\n[OK] LaTeX reconstruction complete!")
                print(f"Generated files:")
                
                if latex_results.get('structured_json'):
                    print(f"  ✓ Structured JSON: {Path(latex_results['structured_json']).name}")
                
                if latex_results.get('markdown'):
                    print(f"  ✓ Markdown: {Path(latex_results['markdown']).name}")
                
                if latex_results.get('latex'):
                    print(f"  ✓ LaTeX source: {Path(latex_results['latex']).name}")
                
                if latex_results.get('pdf'):
                    print(f"  ✓ Compiled PDF: {Path(latex_results['pdf']).name}")
                
                if latex_results.get('assets'):
                    print(f"  ✓ Assets directory: {Path(latex_results['assets']).name}/")
                
                if latex_results.get('images_metadata'):
                    print(f"  ✓ Images metadata: {Path(latex_results['images_metadata']).name}")
                
            except Exception as e:
                print(f"\n[WARN] LaTeX reconstruction failed: {e}")
                print("[INFO] Main JSON extraction succeeded, continuing without LaTeX outputs...")
                import traceback
                traceback.print_exc()
        
        return validated_data
    
    def process_directory(self, directory_path: str, output_dir: str = None):
        """
        Process all supported documents in a directory
        
        Args:
            directory_path: Path to directory containing documents
            output_dir: Optional custom output directory
        """
        directory = Path(directory_path)
        
        if not directory.exists() or not directory.is_dir():
            raise ValueError(f"Invalid directory: {directory}")
        
        # Find all supported files
        files = []
        for ext in SUPPORTED_FORMATS:
            files.extend(directory.glob(f"*{ext}"))
        
        if not files:
            print(f"No supported files found in {directory}")
            return
        
        print(f"\nFound {len(files)} document(s) to process")
        
        results = []
        for file_path in files:
            try:
                # Don't pass output_path - let process_document() determine subfolder based on method used
                result = self.process_document(str(file_path), None)
                results.append({
                    "file": file_path.name,
                    "status": "success",
                    "questions": len(result.get("questions", []))
                })
            except Exception as e:
                print(f"\n[ERROR] Error processing {file_path.name}: {e}")
                results.append({
                    "file": file_path.name,
                    "status": "error",
                    "error": str(e)
                })
        
        # Print summary
        print(f"\n{'='*60}")
        print("PROCESSING SUMMARY")
        print(f"{'='*60}")
        
        success_count = sum(1 for r in results if r["status"] == "success")
        print(f"Successfully processed: {success_count}/{len(results)}")
        
        for result in results:
            status_icon = "[OK]" if result["status"] == "success" else "[FAIL]"
            if result["status"] == "success":
                print(f"{status_icon} {result['file']}: {result['questions']} questions")
            else:
                print(f"{status_icon} {result['file']}: {result.get('error', 'Unknown error')}")

