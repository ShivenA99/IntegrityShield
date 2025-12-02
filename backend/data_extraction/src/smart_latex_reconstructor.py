"""
Smart LaTeX Reconstructor - AI-First Approach (No Regex!)

Uses GPT-4 Vision to analyze the original PDF visually and generate
layout-faithful LaTeX without any regex post-processing.

Key Principles:
1. Let AI SEE the original PDF (multimodal)
2. Provide rich context (OCR data, positioning, extracted images)
3. Give AI FULL responsibility for layout decisions
4. NO regex post-processing (AI gets it right the first time)
5. Smart few-shot examples to guide AI behavior
"""

import base64
import json
import os
import re
import subprocess
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import fitz  # PyMuPDF
from .docling_image_extractor import DoclingImageExtractor
from .document_readers import is_text_quality_good


class SmartLaTeXReconstructor:
    """
    AI-first LaTeX reconstruction without regex hacks
    
    Architecture:
    1. Convert PDF pages to high-quality images
    2. Extract OCR data with Mistral (text + positioning)
    3. Extract images with Docling/PyMuPDF (logos, figures)
    4. Send EVERYTHING to GPT-4 Vision:
       - Original PDF images (what it LOOKS like)
       - OCR structured data (what it CONTAINS)
       - Extracted images (what to INCLUDE)
       - Smart prompt (HOW to reconstruct)
    5. GPT-4 generates perfect LaTeX (minimal post-processing for compilation fixes)
    
    The reconstruction process is designed to be robust with multiple fallback
    mechanisms and comprehensive error handling.
    """
    
    # Constants
    DEFAULT_PDF_DPI = 150  # Balanced DPI for GPT-4 Vision analysis (reduced from 300 for speed)
    DEFAULT_PAGE_LIMIT = 5  # Max pages to send to GPT-4 Vision (token limits)
    BLACK_THRESHOLD = 10  # Threshold for background removal
    BACKGROUND_RATIO_THRESHOLD = 0.3  # 30% black = likely background
    LATEX_COMPILE_TIMEOUT = 60  # Seconds
    LATEX_COMPILE_PASSES = 2  # Number of compilation passes for references
    
    # Model names
    OPENAI_MODEL = "gpt-4o"
    MISTRAL_MODEL = "pixtral-large-latest"
    
    # LaTeX settings
    LATEX_MAX_TOKENS = 8192
    LATEX_TEMPERATURE = 0.1
    
    def __init__(self, openai_api_key: Optional[str] = None, mistral_api_key: Optional[str] = None):
        """Initialize with API keys"""
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.mistral_api_key = mistral_api_key or os.getenv("MISTRAL_API_KEY")
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for smart reconstruction")
        
        # Initialize modular image extractors
        self.docling_extractor = DoclingImageExtractor()
        
        # Initialize timing logger
        self.timing_log = []
        self.step_timers = {}  # Track start times for each step
    
    # ============================================================================
    # Helper Methods
    # ============================================================================
    
    def _start_timer(self, step_name: str):
        """
        Start timing for a specific step.
        
        Args:
            step_name: Name of the step being timed
        """
        self.step_timers[step_name] = time.time()
    
    def _end_timer(self, step_name: str, additional_info: Optional[Dict[str, Any]] = None) -> float:
        """
        End timing for a specific step and record the duration.
        
        Args:
            step_name: Name of the step being timed
            additional_info: Optional dictionary with additional metadata (e.g., page count, image count)
            
        Returns:
            Duration in seconds
        """
        if step_name not in self.step_timers:
            print(f"[WARN] Timer for step '{step_name}' was never started")
            return 0.0
        
        start_time = self.step_timers.pop(step_name)
        end_time = time.time()
        duration = end_time - start_time
        
        # Record timing information
        log_entry = {
            "step": step_name,
            "start_time": datetime.fromtimestamp(start_time).isoformat(),
            "end_time": datetime.fromtimestamp(end_time).isoformat(),
            "duration_seconds": round(duration, 3),
            "duration_formatted": self._format_duration(duration)
        }
        
        # Add additional info if provided
        if additional_info:
            log_entry.update(additional_info)
        
        self.timing_log.append(log_entry)
        
        return duration
    
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
    
    def _save_timing_log(self, output_dir: str, pdf_name: str) -> str:
        """
        Save timing log to a JSON file in the logging folder.
        
        Args:
            output_dir: Output directory path
            pdf_name: Name of the PDF being processed
            
        Returns:
            Path to the saved timing log file
        """
        # Create logging directory
        logging_dir = os.path.join(output_dir, "logging")
        os.makedirs(logging_dir, exist_ok=True)
        
        # Calculate total duration
        total_duration = sum(entry["duration_seconds"] for entry in self.timing_log)
        
        # Calculate summary statistics
        summary = {
            "total_steps": len(self.timing_log)
        }
        
        if self.timing_log:
            fastest = min(self.timing_log, key=lambda x: x["duration_seconds"])
            slowest = max(self.timing_log, key=lambda x: x["duration_seconds"])
            summary["fastest_step"] = {
                "step": fastest["step"],
                "duration_seconds": fastest["duration_seconds"],
                "duration_formatted": fastest["duration_formatted"]
            }
            summary["slowest_step"] = {
                "step": slowest["step"],
                "duration_seconds": slowest["duration_seconds"],
                "duration_formatted": slowest["duration_formatted"]
            }
        else:
            summary["fastest_step"] = None
            summary["slowest_step"] = None
        
        # Create comprehensive log structure
        log_data = {
            "pdf_name": pdf_name,
            "timestamp": datetime.now().isoformat(),
            "total_duration_seconds": round(total_duration, 3),
            "total_duration_formatted": self._format_duration(total_duration),
            "steps": self.timing_log,
            "summary": summary
        }
        
        # Save to JSON file
        log_filename = f"{pdf_name}_timing_log.json"
        log_path = os.path.join(logging_dir, log_filename)
        
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        # Also create a human-readable text log
        text_log_path = os.path.join(logging_dir, f"{pdf_name}_timing_log.txt")
        with open(text_log_path, 'w', encoding='utf-8') as f:
            f.write(f"Pipeline Timing Log: {pdf_name}\n")
            f.write(f"{'='*70}\n\n")
            f.write(f"Generated: {log_data['timestamp']}\n")
            f.write(f"Total Duration: {log_data['total_duration_formatted']} ({total_duration:.3f} seconds)\n\n")
            f.write(f"{'='*70}\n")
            f.write(f"{'Step':<40} {'Duration':<15} {'Additional Info'}\n")
            f.write(f"{'-'*70}\n")
            
            for entry in self.timing_log:
                step_name = entry["step"]
                duration = entry["duration_formatted"]
                info_parts = []
                
                # Add additional info if available
                for key, value in entry.items():
                    if key not in ["step", "start_time", "end_time", "duration_seconds", "duration_formatted"]:
                        info_parts.append(f"{key}={value}")
                
                info_str = ", ".join(info_parts) if info_parts else "-"
                f.write(f"{step_name:<40} {duration:<15} {info_str}\n")
            
            f.write(f"\n{'='*70}\n")
            f.write("Summary:\n")
            if log_data["summary"]["fastest_step"]:
                f.write(f"  Fastest Step: {log_data['summary']['fastest_step']['step']} ({log_data['summary']['fastest_step']['duration_formatted']})\n")
            if log_data["summary"]["slowest_step"]:
                f.write(f"  Slowest Step: {log_data['summary']['slowest_step']['step']} ({log_data['summary']['slowest_step']['duration_formatted']})\n")
        
        return log_path
    
    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """
        Parse JSON from API response, handling various formats.
        
        Args:
            content: Raw response content that may contain JSON
            
        Returns:
            Parsed JSON as dictionary, or raw content wrapped in dict
        """
        # Try to extract JSON from code fences
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"raw_content": content}
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0].strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                return {"raw_content": content}
        else:
            # Try to parse entire content as JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_content": content}
    
    def _classify_image_position(self, y_pos: float, page_height: float) -> str:
        """
        Classify image position based on vertical location.
        
        Args:
            y_pos: Y coordinate of image (top edge)
            page_height: Total height of the page
            
        Returns:
            Position type: "header/logo", "footer", or "content"
        """
        header_threshold = page_height * 0.2  # Top 20% of page
        footer_threshold = page_height * 0.8  # Bottom 20% of page
        
        if y_pos < header_threshold:
            return "header/logo"
        elif y_pos > footer_threshold:
            return "footer"
        else:
            return "content"
    
    def _get_empty_visual_content(self) -> Dict[str, Any]:
        """
        Return empty visual content structure.
        
        Returns:
            Dictionary with empty visual content structure
        """
        return {
            "all_elements": [],
            "missing_images": [],
            "summary": {
                "total_elements": 0,
                "extracted_by_pymupdf": 0,
                "missed_by_pymupdf": 0
            }
        }
    
    # ============================================================================
    # Main Pipeline Methods
    # ============================================================================
    
    def load_json_data(self, json_path: str) -> Optional[Dict[str, Any]]:
        """Load structured JSON data from file"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to load JSON data from {json_path}: {e}")
            return None
    
    def reconstruct_pdf_to_latex(
        self,
        pdf_path: str,
        output_dir: str,
        include_images: bool = True,
        compile_pdf: bool = True,
        json_data: Optional[Dict[str, Any]] = None,
        external_timings: Optional[Dict[str, Any]] = None,
        enable_visual_detection: bool = False,
        use_mistral_ocr: bool = False,
        skip_ocr_if_text_good: bool = True,
        text_quality_good: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: PDF → Smart LaTeX reconstruction
        
        Args:
            pdf_path: Path to input PDF
            output_dir: Directory for outputs
            include_images: Whether to extract and include images
            compile_pdf: Whether to compile LaTeX to PDF
            json_data: Optional structured JSON data
            external_timings: Optional dict with 'initialization' (list) and 'chunking' (dict) timings
            enable_visual_detection: Whether to run visual content detection (default: False for speed)
            use_mistral_ocr: Whether to use Mistral OCR (default: False for speed)
            skip_ocr_if_text_good: Skip OCR if text quality is already good (default: True)
            text_quality_good: Optional text quality status from main pipeline (None = auto-check)
            
        Returns:
            Dict with paths to generated files
        """
        # Reset timing log for new run
        self.timing_log = []
        self.step_timers = {}
        
        # Prepend external timings (initialization and chunking) if provided
        if external_timings:
            # Add initialization timings first (they happen earliest)
            if "initialization" in external_timings and external_timings["initialization"]:
                for init_timing in external_timings["initialization"]:
                    self.timing_log.append(init_timing)
            
            # Add chunking timing if available
            if "chunking" in external_timings and external_timings["chunking"]:
                self.timing_log.append(external_timings["chunking"])
        
        # Start overall pipeline timer
        self._start_timer("pipeline_total")
        pdf_name = Path(pdf_path).stem
        
        print(f"\n{'='*70}")
        print(f"Smart LaTeX Reconstruction (AI-First, No Regex!)")
        print(f"{'='*70}\n")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Step 1: Convert PDF to images (for GPT-4 Vision)
        print("[1/6] Converting PDF pages to images for visual analysis...")
        self._start_timer("pdf_to_images_conversion")
        pdf_images = self._pdf_to_images(pdf_path, output_dir)
        self._end_timer("pdf_to_images_conversion", {"pages_converted": len(pdf_images)})
        print(f"[OK] Converted {len(pdf_images)} page(s) to images")
        
        # Step 2 & 3: Extract OCR data and images in parallel for speed
        print("\n[2-3/6] Extracting OCR data and images in parallel...")
        ocr_data = None
        extracted_images = []
        assets_dir = None
        images_metadata_path = None
        
        # Check if we should skip OCR based on text quality
        should_skip_ocr = False
        if use_mistral_ocr and skip_ocr_if_text_good:
            # Determine text quality status
            if text_quality_good is not None:
                # Use provided quality status from main pipeline
                should_skip_ocr = text_quality_good
                if should_skip_ocr:
                    print("[INFO] Text quality is good - skipping Mistral OCR (provided by main pipeline)")
            else:
                # Auto-check text quality by extracting with PyMuPDF
                try:
                    doc = fitz.open(pdf_path)
                    text = ""
                    for page in doc:
                        text += page.get_text()
                    doc.close()
                    
                    if is_text_quality_good(text):
                        should_skip_ocr = True
                        print("[INFO] Text quality is good - skipping Mistral OCR (auto-detected)")
                    else:
                        print("[INFO] Text quality is poor - will use Mistral OCR")
                except Exception as e:
                    print(f"[WARN] Could not check text quality: {e} - will attempt OCR")
        
        # Helper function for image extraction
        def extract_images_task():
            """Extract images using Docling or PyMuPDF"""
            if not include_images:
                return []
            
            assets_dir_local = os.path.join(output_dir, f"{pdf_name}_assets")
            
            # Try Docling first (better for complex layouts)
            if self.docling_extractor.is_available():
                return self.docling_extractor.extract_images(pdf_path, assets_dir_local), "docling", assets_dir_local
            else:
                # Fallback to PyMuPDF
                return self._extract_all_images(pdf_path, assets_dir_local), "pymupdf", assets_dir_local
        
        # Run OCR and image extraction in parallel
        # Start timers before parallel execution
        ocr_future = None
        image_future = None
        
        # Only run OCR if explicitly requested AND not skipped due to good text quality
        should_run_ocr = use_mistral_ocr and self.mistral_api_key and not should_skip_ocr
        
        if should_run_ocr:
            self._start_timer("mistral_ocr_extraction")
        
        if include_images:
            if self.docling_extractor.is_available():
                self._start_timer("docling_image_extraction")
            else:
                self._start_timer("pymupdf_image_extraction")
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            if should_run_ocr:
                ocr_future = executor.submit(self._extract_ocr_data, pdf_path)
            if include_images:
                image_future = executor.submit(extract_images_task)
            
            # Wait for OCR to complete
            if ocr_future:
                try:
                    ocr_data = ocr_future.result()
                    if ocr_data:
                        pages_count = len(ocr_data.get('pages', []))
                        self._end_timer("mistral_ocr_extraction", {"pages_processed": pages_count})
                        print(f"[OK] Extracted OCR data from {pages_count} page(s)")
                    else:
                        self._end_timer("mistral_ocr_extraction", {"success": False})
                        print("[WARN] Mistral OCR returned no data")
                except Exception as e:
                    self._end_timer("mistral_ocr_extraction", {"success": False, "error": str(e)})
                    print(f"[WARN] Mistral OCR failed: {e}")
            elif should_skip_ocr:
                print("[INFO] Mistral OCR skipped - text quality is good, using visual analysis only")
            else:
                print("[INFO] Mistral OCR skipped - will use visual analysis only")
            
            # Wait for image extraction to complete
            if image_future:
                try:
                    result = image_future.result()
                    extracted_images, extraction_method, assets_dir = result
                    
                    if extraction_method == "docling":
                        self._end_timer("docling_image_extraction", {
                            "images_extracted": len(extracted_images),
                            "method": "docling"
                        })
                    else:
                        self._end_timer("pymupdf_image_extraction", {
                            "images_extracted": len(extracted_images),
                            "method": "pymupdf"
                        })
                    
                    if not extracted_images:
                        print("[INFO] No images extracted")
                    else:
                        print(f"[OK] Extracted {len(extracted_images)} image(s) using {extraction_method}")
                except Exception as e:
                    # End timer even on failure
                    if self.docling_extractor.is_available():
                        self._end_timer("docling_image_extraction", {"success": False, "error": str(e)})
                    else:
                        self._end_timer("pymupdf_image_extraction", {"success": False, "error": str(e)})
                    print(f"[WARN] Image extraction failed: {e}")
                    extracted_images = []
                    assets_dir = None
        
        # Save image metadata if images were extracted
        if extracted_images:
            self._start_timer("save_image_metadata")
            images_metadata_path = os.path.join(output_dir, f"{pdf_name}_images.json")
            self._save_images_metadata(extracted_images, images_metadata_path)
            self._end_timer("save_image_metadata", {"images_saved": len(extracted_images)})
            print(f"[OK] Saved image metadata: {Path(images_metadata_path).name}")
        
        # Step 4: Visual Content Detection with GPT-4 Vision (optional for speed)
        if enable_visual_detection:
            print("\n[4/6] Detecting all visual content with GPT-4 Vision...")
            self._start_timer("visual_content_detection")
            visual_content = self._detect_visual_content_with_gpt4v(pdf_images, extracted_images)
            
            # Log detection results
            total_elements = visual_content.get('summary', {}).get('total_elements', 0)
            extracted_by_pymupdf = visual_content.get('summary', {}).get('extracted_by_pymupdf', 0)
            missed_by_pymupdf = visual_content.get('summary', {}).get('missed_by_pymupdf', 0)
            
            self._end_timer("visual_content_detection", {
                "total_elements": total_elements,
                "extracted_by_pymupdf": extracted_by_pymupdf,
                "missed_by_pymupdf": missed_by_pymupdf
            })
            
            print(f"[OK] Visual content detection completed")
            print(f"[INFO] Total elements detected: {total_elements}")
            print(f"[INFO] PyMuPDF captured: {extracted_by_pymupdf}")
            print(f"[INFO] Missing elements: {missed_by_pymupdf}")
        else:
            print("\n[4/6] Skipping visual content detection (disabled for speed)")
            visual_content = self._get_empty_visual_content()
        
        # Step 5: Prepare rich context for GPT-4 Vision
        print("\n[5/6] Preparing rich context for AI analysis...")
        self._start_timer("build_rich_context")
        context = self._build_rich_context(
            pdf_path=pdf_path,
            pdf_images=pdf_images,
            ocr_data=ocr_data,
            extracted_images=extracted_images,
            assets_dir=assets_dir,
            json_data=json_data,
            visual_content=visual_content
        )
        self._end_timer("build_rich_context", {
            "pages_encoded": len(context.get('original_pages', [])),
            "images_encoded": len(context.get('extracted_images', []))
        })
        print("[OK] Context prepared")
        
        # Step 6: Generate LaTeX with GPT-4 Vision (the smart part!)
        print("\n[6/6] Generating layout-faithful LaTeX with GPT-4 Vision...")
        self._start_timer("latex_generation_gpt4v")
        latex_code = self._generate_smart_latex(context)
        self._end_timer("latex_generation_gpt4v", {
            "latex_length": len(latex_code),
            "model": self.OPENAI_MODEL
        })
        
        # Save LaTeX
        self._start_timer("save_latex_file")
        latex_path = os.path.join(output_dir, f"{pdf_name}.tex")
        with open(latex_path, "w", encoding="utf-8") as f:
            f.write(latex_code)
        self._end_timer("save_latex_file", {"file_size_bytes": len(latex_code.encode('utf-8'))})
        print(f"[OK] Generated LaTeX: {latex_path}")
        
        # Step 6.5: Generate Markdown for text extraction analysis
        print("\n[6.5/6] Generating Markdown for text extraction analysis...")
        self._start_timer("markdown_generation")
        markdown_path = self._generate_markdown(context, output_dir)
        if markdown_path:
            self._end_timer("markdown_generation", {"success": True})
            print(f"[OK] Generated Markdown: {Path(markdown_path).name}")
        else:
            self._end_timer("markdown_generation", {"success": False})
        
        # Step 7: Compile to PDF (optional)
        pdf_output_path = None
        if compile_pdf:
            print("\n[7/7] Compiling LaTeX to PDF...")
            self._start_timer("latex_compilation")
            pdf_output_path = self._compile_latex(latex_path, output_dir)
            if pdf_output_path:
                pdf_size = os.path.getsize(pdf_output_path) if os.path.exists(pdf_output_path) else 0
                self._end_timer("latex_compilation", {
                    "success": True,
                    "pdf_size_bytes": pdf_size
                })
                print(f"[OK] Compiled PDF: {pdf_output_path}")
            else:
                self._end_timer("latex_compilation", {"success": False})
                print("[WARN] LaTeX compilation failed")
        
        # Generate visual gap report
        self._start_timer("visual_gap_report_generation")
        visual_gap_report = self._generate_visual_gap_report(visual_content, output_dir)
        self._end_timer("visual_gap_report_generation", {"report_generated": visual_gap_report is not None})
        
        # End overall pipeline timer and save timing log
        self._end_timer("pipeline_total", {
            "total_steps": len(self.timing_log) - 1,  # Exclude pipeline_total itself
            "include_images": include_images,
            "compile_pdf": compile_pdf
        })
        
        # Save timing log to file
        timing_log_path = self._save_timing_log(output_dir, pdf_name)
        print(f"\n[OK] Timing log saved: {Path(timing_log_path).name}")
        
        return {
            "latex": latex_path,
            "pdf": pdf_output_path,
            "assets": assets_dir,
            "images_metadata": images_metadata_path,
            "original_images": pdf_images,
            "extracted_images": extracted_images,
            "visual_gap_report": visual_gap_report,
            "markdown": markdown_path,
            "timing_log": timing_log_path
        }
    
    def _pdf_to_images(self, pdf_path: str, output_dir: str, dpi: int = None) -> List[str]:
        """
        Convert PDF pages to high-quality images for GPT-4 Vision analysis.
        
        Args:
            pdf_path: Path to input PDF file
            output_dir: Directory to save page images
            dpi: Resolution for image rendering (defaults to DEFAULT_PDF_DPI)
            
        Returns:
            List of paths to generated page images
        """
        if dpi is None:
            dpi = self.DEFAULT_PDF_DPI
            
        doc = fitz.open(pdf_path)
        image_paths = []
        images_dir = os.path.join(output_dir, "original_pages")
        os.makedirs(images_dir, exist_ok=True)
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Render page to image at specified DPI
                # PyMuPDF default is 72 DPI, so we scale by dpi/72
                scale_factor = dpi / 72.0
                mat = fitz.Matrix(scale_factor, scale_factor)
                pix = page.get_pixmap(matrix=mat)
                
                # Save as PNG
                img_path = os.path.join(images_dir, f"page_{page_num + 1}.png")
                pix.save(img_path)
                image_paths.append(img_path)
        finally:
            doc.close()
            
        return image_paths
    
    def _extract_ocr_data(self, pdf_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract structured OCR data using Mistral Document AI.
        
        Args:
            pdf_path: Path to input PDF file
            
        Returns:
            Dictionary with OCR data, or None if extraction fails
        """
        if not self.mistral_api_key:
            return None
        
        try:
            from mistralai import Mistral
            
            client = Mistral(api_key=self.mistral_api_key)
            
            # Read PDF and encode as base64
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
                pdf_data = base64.b64encode(pdf_bytes).decode("utf-8")
            
            # Call Mistral Document AI API with timeout
            response = client.chat.complete(
                model=self.MISTRAL_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document_url",
                                "document_url": f"data:application/pdf;base64,{pdf_data}"
                            },
                            {
                                "type": "text",
                                "text": "Extract all text content with structure and positioning information."
                            }
                        ]
                    }
                ],
                timeout=30.0  # 30 second timeout to fail fast
            )
            
            # Extract and parse response content
            content = response.choices[0].message.content
            return self._parse_json_response(content)
                
        except ImportError:
            print(f"[WARN] Mistral AI library not installed")
            return None
        except TimeoutError:
            print(f"[WARN] Mistral OCR timed out after 30 seconds")
            return None
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "timed out" in error_msg:
                print(f"[WARN] Mistral OCR timed out: {e}")
            else:
                print(f"[WARN] Mistral OCR failed: {e}")
            return None
    
    
    def _extract_all_images(self, pdf_path: str, assets_dir: str) -> List[Dict[str, Any]]:
        """
        Extract all images from PDF using PyMuPDF (fallback method).
        
        This method extracts images with metadata including bounding boxes,
        position classification, and dimensions.
        
        Args:
            pdf_path: Path to input PDF file
            assets_dir: Directory to save extracted images
            
        Returns:
            List of dictionaries containing image metadata
        """
        os.makedirs(assets_dir, exist_ok=True)
        doc = fitz.open(pdf_path)
        extracted = []
        
        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_height = page.rect.height
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    
                    try:
                        # Extract image data
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Get bounding box coordinates
                        rects = page.get_image_rects(xref)
                        bbox = list(rects[0]) if rects else [0, 0, 0, 0]
                        
                        # Classify image position based on vertical location
                        y_pos = bbox[1] if len(bbox) > 1 else 0
                        position_type = self._classify_image_position(y_pos, page_height)
                        
                        # Save image to disk
                        filename = f"page{page_num + 1}_img{img_index + 1}.{image_ext}"
                        img_path = os.path.join(assets_dir, filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # Attempt background removal (non-critical, continues on failure)
                        try:
                            self._remove_black_background(img_path)
                        except Exception:
                            pass  # Background removal is optional
                        
                        # Build image metadata dictionary
                        extracted.append({
                            "filename": filename,
                            "path": img_path,
                            "page": page_num + 1,
                            "bbox": bbox,
                            "position_type": position_type,
                            "width": bbox[2] - bbox[0] if len(bbox) > 2 else 0,
                            "height": bbox[3] - bbox[1] if len(bbox) > 3 else 0
                        })
                        
                    except Exception as e:
                        print(f"[WARN] Failed to extract image {img_index + 1} from page {page_num + 1}: {e}")
                        continue
        finally:
            doc.close()
            
        return extracted
    
    def _save_images_metadata(self, extracted_images: List[Dict[str, Any]], json_path: str):
        """
        Save extracted images metadata to a structured JSON file
        
        Args:
            extracted_images: List of image metadata dictionaries
            json_path: Path where to save the JSON file
        """
        # Prepare clean metadata (remove base64 data if present)
        metadata = {
            "total_images": len(extracted_images),
            "images": []
        }
        
        for img in extracted_images:
            img_data = {
                "filename": img["filename"],
                "page": img["page"],
                "position_type": img["position_type"],
                "bbox": {
                    "x1": img["bbox"][0],
                    "y1": img["bbox"][1],
                    "x2": img["bbox"][2],
                    "y2": img["bbox"][3]
                },
                "dimensions": {
                    "width": img["width"],
                    "height": img["height"]
                },
                "path": img["path"]
            }
            metadata["images"].append(img_data)
        
        # Save to JSON file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def _remove_black_background(self, image_path: str):
        """
        Remove black backgrounds from images while preserving text and graphics.
        
        Uses a smart flood-fill approach that only removes edge-connected black
        regions, preserving text and detailed graphics.
        
        Args:
            image_path: Path to image file to process
        """
        try:
            from PIL import Image
            import numpy as np
            
            img = Image.open(image_path)
            
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            data = np.array(img)
            height, width = data.shape[:2]
            
            # Identify very dark pixels (below threshold)
            # Conservative threshold avoids removing anti-aliased text edges
            dark_mask = (
                (data[:, :, 0] < self.BLACK_THRESHOLD) &
                (data[:, :, 1] < self.BLACK_THRESHOLD) &
                (data[:, :, 2] < self.BLACK_THRESHOLD)
            )
            
            # Only process if significant portion is black (likely has background)
            black_ratio = np.sum(dark_mask) / (height * width)
            
            if black_ratio > self.BACKGROUND_RATIO_THRESHOLD:
                # Use a smarter approach: flood fill from edges
                # This removes connected background regions but preserves text
                
                # Create a mask for edge-connected black regions
                from scipy import ndimage
                
                # Start from edges
                edge_mask = np.zeros_like(dark_mask)
                edge_mask[0, :] = dark_mask[0, :]  # Top edge
                edge_mask[-1, :] = dark_mask[-1, :]  # Bottom edge
                edge_mask[:, 0] = dark_mask[:, 0]  # Left edge
                edge_mask[:, -1] = dark_mask[:, -1]  # Right edge
                
                # Find connected components from edges
                labeled, num_features = ndimage.label(dark_mask)
                edge_labels = np.unique(labeled[edge_mask])
                edge_labels = edge_labels[edge_labels > 0]  # Remove 0 (no label)
                
                # Create mask for edge-connected black regions only
                background_mask = np.isin(labeled, edge_labels)
                
                # Convert background to white, preserve text
                data[background_mask] = [255, 255, 255, 255]
                
                result = Image.fromarray(data)
                result.save(image_path)
                print(f"    ✓ Smart background removal: {os.path.basename(image_path)}")
            else:
                # Not much black, probably not a background - leave as is
                print(f"    ℹ No black background detected: {os.path.basename(image_path)}")
            
        except ImportError:
            # scipy not available, use simple threshold fallback
            print(f"    ⚠ scipy not available, using simple threshold for: {os.path.basename(image_path)}")
            try:
                from PIL import Image
                import numpy as np
                
                img = Image.open(image_path)
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                data = np.array(img)
                
                # Very conservative threshold - only pure black
                black_threshold_fallback = 5
                black_mask = (
                    (data[:, :, 0] < black_threshold_fallback) &
                    (data[:, :, 1] < black_threshold_fallback) &
                    (data[:, :, 2] < black_threshold_fallback)
                )
                data[black_mask] = [255, 255, 255, 255]
                
                result = Image.fromarray(data)
                result.save(image_path)
            except:
                pass  # Silently continue
        except Exception as e:
            # Any other error, just skip
            print(f"    ⚠ Background removal failed for {os.path.basename(image_path)}: {e}")
            pass
    
    def _detect_visual_content_with_gpt4v(self, pdf_images: List[str], extracted_images: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Use GPT-4 Vision to identify ALL visual content, including what PyMuPDF missed
        
        Args:
            pdf_images: List of paths to PDF page images
            extracted_images: List of images already extracted by PyMuPDF
            
        Returns:
            Dict with detected visual elements and their metadata
        """
        from openai import OpenAI
        
        client = OpenAI(api_key=self.openai_api_key)
        
        # Build extracted images info for comparison
        extracted_info = []
        for img in extracted_images:
            extracted_info.append(f"- {img['filename']} (page {img['page']}, {img['position_type']}, bbox: {img['bbox']})")
        
        # Create visual detection prompt
        detection_prompt = f"""
        You are a visual content analyzer for documents. Analyze these PDF pages and identify ALL visual content that should be preserved in LaTeX.
        
        CURRENT EXTRACTIONS: PyMuPDF found {len(extracted_images)} images:
        {chr(10).join(extracted_info) if extracted_info else "None"}
        
        Your task: Identify ALL visual elements that should be preserved in LaTeX, including:
        1. Embedded images (already extracted by PyMuPDF)
        2. Vector diagrams and illustrations
        3. Charts, graphs, and data visualizations
        4. Complex multi-part figures
        5. Text rendered as graphics
        6. Any visual content that contributes to understanding
        
        For each visual element you identify, provide:
        - element_id: unique identifier
        - type: "extracted_image", "vector_diagram", "chart", "scientific_figure", "text_as_graphics", "logo", "decoration"
        - description: what it shows
        - page_number: which page it's on
        - bounding_box: [x1, y1, x2, y2] coordinates (approximate)
        - pymupdf_captured: true/false (whether PyMuPDF already extracted it)
        - latex_suggestion: how to represent it in LaTeX
        - complexity: "simple", "moderate", "complex"
        
        Pay special attention to:
        - Scientific diagrams that might be vector-based
        - Multi-part figures that should be treated as units
        - Text rendered as graphics
        - Complex illustrations that PyMuPDF might have missed
        - Charts and graphs
        - Logos and decorative elements
        
        Return your analysis as structured JSON with this format:
        {{
            "all_elements": [
                {{
                    "element_id": "elem_1",
                    "type": "extracted_image",
                    "description": "Biological cell diagram",
                    "page_number": 1,
                    "bounding_box": [65.76, 185.70, 195.36, 365.22],
                    "pymupdf_captured": true,
                    "latex_suggestion": "\\includegraphics{{page1_img1.png}}",
                    "complexity": "moderate"
                }}
            ],
            "missing_images": [
                // Elements where pymupdf_captured = false
            ],
            "summary": {{
                "total_elements": 15,
                "extracted_by_pymupdf": 7,
                "missed_by_pymupdf": 8,
                "complexity_breakdown": {{
                    "simple": 5,
                    "moderate": 7,
                    "complex": 3
                }}
            }}
        }}
        """
        
        # Build multimodal messages
        messages = [
            {
                "role": "system",
                "content": "You are an expert visual content analyzer. Analyze documents to identify ALL visual elements that should be preserved in LaTeX reconstruction."
            },
            {
                "role": "user",
                "content": self._build_visual_detection_prompt(pdf_images, detection_prompt)
            }
        ]
        
        try:
            # Call GPT-4 Vision API
            response = client.chat.completions.create(
                model=self.OPENAI_MODEL,
                messages=messages,
                max_tokens=self.LATEX_MAX_TOKENS,
                temperature=self.LATEX_TEMPERATURE
            )
            
            # Extract and parse response
            content = response.choices[0].message.content
            visual_content = self._parse_json_response(content)
            
            # Log detection results
            summary = visual_content.get('summary', {})
            print(f"[OK] Visual content detection completed")
            print(f"[INFO] Total elements detected: {summary.get('total_elements', 0)}")
            print(f"[INFO] PyMuPDF captured: {summary.get('extracted_by_pymupdf', 0)}")
            print(f"[INFO] Missing elements: {summary.get('missed_by_pymupdf', 0)}")
            
            # Ensure proper structure even if parsing returned raw content
            if 'summary' not in visual_content:
                visual_content['summary'] = {
                    'total_elements': 0,
                    'extracted_by_pymupdf': 0,
                    'missed_by_pymupdf': 0
                }
            
            return visual_content
                
        except json.JSONDecodeError as e:
            print(f"[WARN] Failed to parse visual content JSON: {e}")
            return self._get_empty_visual_content()
                
        except Exception as e:
            print(f"[WARN] Visual content detection failed: {e}")
            return self._get_empty_visual_content()
    
    def _build_visual_detection_prompt(self, pdf_images: List[str], detection_prompt: str) -> List[Dict[str, Any]]:
        """
        Build multimodal prompt for visual content detection.
        
        Args:
            pdf_images: List of paths to PDF page images
            detection_prompt: Text prompt describing the detection task
            
        Returns:
            List of message content dictionaries for GPT-4 Vision API
        """
        content = []
        
        # Add instruction text
        content.append({"type": "text", "text": detection_prompt})
        
        # Add PDF page images (limit to avoid token limits)
        for img_path in pdf_images[:self.DEFAULT_PAGE_LIMIT]:
            try:
                with open(img_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}",
                            "detail": "high"
                        }
                    })
            except Exception as e:
                print(f"[WARN] Failed to encode image {img_path}: {e}")
                continue
        
        return content
    
    def _detect_hierarchical_numbering(self, text: str) -> Dict[str, Any]:
        """
        Detect hierarchical numbering patterns in the extracted text
        
        Args:
            text: Extracted text content
            
        Returns:
            Dict with detected numbering patterns and structure
        """
        import re
        
        # Look for various hierarchical numbering patterns
        patterns = {
            # Main parts: letters with parentheses (a), b), c), etc.)
            'main_parts_letters': re.findall(r'[a-z]\)\s+[^a-z]*?(?=[a-z]\)|$)', text, re.DOTALL),
            # Main parts: numbers with parentheses (1), 2), 3), etc.)
            'main_parts_numbers': re.findall(r'\d+\)\s+[^\d]*?(?=\d+\)|$)', text, re.DOTALL),
            # Sub-parts: Roman numerals (i., ii., iii., iv., v., etc.)
            'sub_parts_roman': re.findall(r'[ivx]+\.\s+[^ivx]*?(?=[ivx]+\.|$)', text, re.DOTALL),
            # Sub-parts: lowercase letters (a., b., c., etc.)
            'sub_parts_letters': re.findall(r'[a-z]\.\s+[^a-z]*?(?=[a-z]\.|$)', text, re.DOTALL),
            # Sub-parts: numbers (1., 2., 3., etc.)
            'sub_parts_numbers': re.findall(r'\d+\.\s+[^\d]*?(?=\d+\.|$)', text, re.DOTALL),
            # Nested structures: main part followed by sub-parts
            'nested_structures': re.findall(r'[a-z]\)\s+[^a-z]*?(?:[ivx]+\.\s+[^ivx]*?)*', text, re.DOTALL)
        }
        
        # Count total patterns found
        total_main_parts = len(patterns['main_parts_letters']) + len(patterns['main_parts_numbers'])
        total_sub_parts = (len(patterns['sub_parts_roman']) + 
                          len(patterns['sub_parts_letters']) + 
                          len(patterns['sub_parts_numbers']))
        
        # Detect if there are sub-parts that should be nested under main parts
        hierarchical_detected = total_sub_parts > 0 and total_main_parts > 0
        
        return {
            'hierarchical_detected': hierarchical_detected,
            'patterns': patterns,
            'needs_nested_enumeration': hierarchical_detected,
            'total_main_parts': total_main_parts,
            'total_sub_parts': total_sub_parts
        }
    
    def _generate_visual_gap_report(self, visual_content: Dict[str, Any], output_dir: str) -> Optional[str]:
        """
        Generate a report of visual content analysis and gaps
        
        Args:
            visual_content: Visual content analysis results
            output_dir: Directory to save the report
            
        Returns:
            Path to the generated report file, or None if no gaps
        """
        if not visual_content or not visual_content.get('missing_images'):
            print("[INFO] No visual gaps detected - all visual content captured")
            return None
        
        missing_elements = visual_content.get('missing_images', [])
        summary = visual_content.get('summary', {})
        
        # Generate report content
        report_content = f"""# Visual Content Analysis Report

## Summary
- **Total visual elements detected:** {summary.get('total_elements', 0)}
- **Successfully extracted by PyMuPDF:** {summary.get('extracted_by_pymupdf', 0)}
- **Missing visual content:** {summary.get('missed_by_pymupdf', 0)}

## Missing Visual Elements
The following visual elements were detected but could not be extracted by PyMuPDF. 
These will be represented in LaTeX using the suggested approaches:

"""
        
        for i, element in enumerate(missing_elements, 1):
            report_content += f"""### {i}. {element.get('type', 'Unknown Type').title()}

- **Description:** {element.get('description', 'No description available')}
- **Page:** {element.get('page_number', 'Unknown')}
- **Bounding Box:** {element.get('bounding_box', 'Unknown')}
- **Complexity:** {element.get('complexity', 'Unknown')}
- **Suggested LaTeX:** {element.get('latex_suggestion', 'No suggestion available')}

"""
        
        # Add complexity breakdown if available
        complexity_breakdown = summary.get('complexity_breakdown', {})
        if complexity_breakdown:
            report_content += f"""## Complexity Breakdown
- **Simple:** {complexity_breakdown.get('simple', 0)} elements
- **Moderate:** {complexity_breakdown.get('moderate', 0)} elements  
- **Complex:** {complexity_breakdown.get('complex', 0)} elements

"""
        
        report_content += """## Notes
- Missing visual content will be represented in LaTeX using appropriate methods
- Vector diagrams will use \\tikz
- Complex figures will use placeholders with descriptions
- Charts and graphs will use LaTeX representations
- All visual information is preserved through intelligent LaTeX generation

## Recommendations
1. Review the generated LaTeX to ensure all visual content is properly represented
2. For complex diagrams, consider manual refinement of the \\tikz code
3. For scientific illustrations, verify that all visual information is preserved
"""
        
        # Save report
        report_path = os.path.join(output_dir, f"{Path(output_dir).name}_visual_gap_report.md")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            print(f"[OK] Visual gap report saved: {Path(report_path).name}")
            return report_path
        except Exception as e:
            print(f"[WARN] Failed to save visual gap report: {e}")
            return None
    
    def _generate_markdown(self, context: Dict[str, Any], output_dir: str) -> Optional[str]:
        """
        Generate Markdown file showing extracted text content for manual inspection
        
        Args:
            context: Rich context with all data sources
            output_dir: Directory to save the markdown file
            
        Returns:
            Path to the generated markdown file, or None if failed
        """
        try:
            pdf_name = context.get('pdf_name', 'document')
            markdown_path = os.path.join(output_dir, f"{pdf_name}.md")
            
            # Build markdown content
            markdown_content = f"""# Extracted Text Content: {pdf_name}

## Document Overview
- **Document:** {context.get('pdf_path', 'Unknown')}
- **Pages:** {len(context.get('original_pages', []))}
- **Extracted Images:** {len(context.get('extracted_images', []))}

---

## OCR Data (Mistral OCR)

"""
            
            # Add OCR data - the actual extracted text
            if context.get('ocr_data'):
                ocr_data = context['ocr_data']
                if isinstance(ocr_data, dict):
                    # If it's a dict, try to extract the raw content
                    if 'raw_content' in ocr_data:
                        markdown_content += ocr_data['raw_content']
                    else:
                        # Show the structured data
                        markdown_content += json.dumps(ocr_data, indent=2)
                else:
                    # If it's a string, show it directly
                    markdown_content += str(ocr_data)
            else:
                markdown_content += "*No OCR data available*"
            
            markdown_content += """

---

## Structured JSON Data (Questions and Sub-questions)

"""
            
            # Add structured JSON data - the questions and sub-questions
            if context.get('json_data'):
                json_data = context['json_data']
                markdown_content += json.dumps(json_data, indent=2)
            else:
                markdown_content += "*No structured JSON data available*"
            
            markdown_content += """

---

## Visual Content Analysis

"""
            
            # Add visual content analysis
            if context.get('visual_content'):
                visual_content = context['visual_content']
                summary = visual_content.get('summary', {})
                
                markdown_content += f"""### Summary
- **Total visual elements detected:** {summary.get('total_elements', 0)}
- **PyMuPDF extractions:** {summary.get('extracted_by_pymupdf', 0)}
- **Missing visual content:** {summary.get('missed_by_pymupdf', 0)}

### Missing Visual Elements
"""
                
                missing_images = visual_content.get('missing_images', [])
                if missing_images:
                    for i, element in enumerate(missing_images, 1):
                        markdown_content += f"""
**{i}. {element.get('type', 'Unknown Type').title()}**
- Description: {element.get('description', 'No description')}
- Page: {element.get('page_number', 'Unknown')}
- Complexity: {element.get('complexity', 'Unknown')}
- Suggested LaTeX: `{element.get('latex_suggestion', 'No suggestion')}`
"""
                else:
                    markdown_content += "*No missing visual elements detected*"
            else:
                markdown_content += "*No visual content analysis available*"
            
            markdown_content += """

---

## Extracted Images (PyMuPDF)

"""
            
            # Add extracted images
            if context.get('extracted_images'):
                for img in context['extracted_images']:
                    markdown_content += f"""
- **{img.get('filename', 'Unknown')}** (Page {img.get('page', 'Unknown')})
  - Type: {img.get('position_type', 'Unknown')}
  - Bounding Box: {img.get('bbox', 'Unknown')}
  - Dimensions: {img.get('width', 'Unknown')} x {img.get('height', 'Unknown')}
"""
            else:
                markdown_content += "*No images extracted*"
            
            markdown_content += """

---

## Manual Inspection Notes

### For Questions and Sub-questions
1. **Check completeness** - Are all questions from the original PDF captured?
2. **Verify sub-questions** - Are all sub-questions properly extracted?
3. **Review formatting** - Is the text properly formatted and readable?
4. **Check special characters** - Are Greek letters, math symbols, etc. preserved?

### For Visual Content
1. **Review extracted images** - Are all important visual elements captured?
2. **Check missing elements** - What visual content was missed by PyMuPDF?
3. **Verify descriptions** - Are the descriptions of missing elements accurate?

### For LaTeX Generation
1. **Text accuracy** - Does the extracted text match the original?
2. **Visual completeness** - Are all visual elements accounted for?
3. **Layout preservation** - Will the LaTeX maintain the original layout?

---
*Generated by Smart LaTeX Reconstructor with Visual Content Detection*
"""
            
            # Save markdown file
            with open(markdown_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            
            return markdown_path
            
        except Exception as e:
            print(f"[WARN] Failed to generate markdown: {e}")
            return None
    
    def _build_rich_context(
        self,
        pdf_path: str,
        pdf_images: List[str],
        ocr_data: Optional[Dict[str, Any]],
        extracted_images: List[Dict[str, Any]],
        assets_dir: Optional[str],
        json_data: Optional[Dict[str, Any]] = None,
        visual_content: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build comprehensive context dictionary for GPT-4 Vision.
        
        Encodes all images as base64 and organizes data sources for
        the LaTeX generation process.
        
        Args:
            pdf_path: Path to input PDF file
            pdf_images: List of paths to PDF page images
            ocr_data: OCR data from Mistral (optional)
            extracted_images: List of extracted image metadata
            assets_dir: Directory containing extracted images
            json_data: Structured JSON data with questions (optional)
            visual_content: Visual content analysis results (optional)
            
        Returns:
            Dictionary containing all context for LaTeX generation
        """
        # Encode PDF page images for GPT-4 Vision
        encoded_pages = []
        for img_path in pdf_images[:self.DEFAULT_PAGE_LIMIT]:
            try:
                with open(img_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                    encoded_pages.append({
                        "path": img_path,
                        "base64": encoded
                    })
            except Exception as e:
                print(f"[WARN] Failed to encode page image {img_path}: {e}")
                continue
        
        # Encode extracted images
        encoded_extracted = []
        for img_info in extracted_images:
            try:
                with open(img_info["path"], "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                    encoded_extracted.append({
                        **img_info,
                        "base64": encoded
                    })
            except Exception as e:
                print(f"[WARN] Failed to encode extracted image {img_info.get('filename', 'unknown')}: {e}")
                continue
        
        return {
            "pdf_path": pdf_path,
            "pdf_name": Path(pdf_path).stem,
            "original_pages": encoded_pages,
            "ocr_data": ocr_data,
            "extracted_images": encoded_extracted,
            "assets_dir": assets_dir,
            "json_data": json_data,  # Add structured JSON data
            "visual_content": visual_content  # Add visual content analysis
        }
    
    def _generate_smart_latex(self, context: Dict[str, Any]) -> str:
        """
        Generate LaTeX using GPT-4 Vision with rich context
        
        This is the SMART part - no regex needed!
        """
        from openai import OpenAI
        
        client = OpenAI(api_key=self.openai_api_key)
        
        # Build multimodal messages
        messages = [
            {
                "role": "system",
                "content": self._get_system_prompt()
            },
            {
                "role": "user",
                "content": self._build_user_prompt(context)
            }
        ]
        
        # Call GPT-4 Vision API
        response = client.chat.completions.create(
            model=self.OPENAI_MODEL,
            messages=messages,
            max_tokens=self.LATEX_MAX_TOKENS,
            temperature=self.LATEX_TEMPERATURE
        )
        
        latex_code = response.choices[0].message.content
        
        # Clean up code fences if present (minimal post-processing)
        if "```latex" in latex_code:
            latex_code = latex_code.split("```latex")[1].split("```")[0].strip()
        elif "```" in latex_code:
            latex_code = latex_code.split("```")[1].split("```")[0].strip()
        
        # Ensure \graphicspath is present (minimal post-processing for images)
        latex_code = self._ensure_graphicspath(latex_code, context)
        
        # Fix common spacing issues (minimal post-processing)
        latex_code = self._fix_metadata_spacing(latex_code)
        
        # Fix package conflicts (critical for compilation)
        latex_code = self._fix_package_conflicts(latex_code)
        
        return latex_code
    
    def _fix_metadata_spacing(self, latex_code: str) -> str:
        r"""
        Fix common spacing issues in metadata lines
        
        Detects lines like:
        Term: 2023 \hfill Subject: Math \hfill Number: 101
        
        And converts to:
        \begin{tabular}{@{}l@{\hspace{2em}}l@{\hspace{2em}}l@{}}
        Term: 2023 & Subject: Math & Number: 101
        \end{tabular}
        """
        import re
        
        lines = latex_code.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Check if line has multiple \hfill separators (metadata pattern)
            if '\\hfill' in line and line.count('\\hfill') >= 2:
                # Check if it looks like metadata (has "Term:", "Subject:", "Course", etc.)
                if any(keyword in line for keyword in ['Term:', 'Subject:', 'Course', 'Number:']):
                    # Split by \hfill
                    parts = [p.strip() for p in line.split('\\hfill')]
                    
                    # Remove \noindent if present
                    if parts[0].startswith('\\noindent'):
                        parts[0] = parts[0].replace('\\noindent', '').strip()
                    
                    # Convert to tabular
                    fixed_line = '\\noindent\n\\begin{tabular}{@{}' + 'l@{\\hspace{2em}}' * len(parts) + '}\n'
                    fixed_line += ' & '.join(parts)
                    fixed_line += '\n\\end{tabular}'
                    
                    fixed_lines.append(fixed_line)
                    print(f"[INFO] Fixed metadata spacing: {len(parts)} fields")
                    continue
            
            fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def _fix_package_conflicts(self, latex_code: str) -> str:
        """
        Fix package conflicts that prevent compilation
        
        Known conflicts:
        1. fontspec + inputenc (fontspec is for XeLaTeX/LuaLaTeX, inputenc is for pdfLaTeX)
        2. Multiple geometry declarations
        3. Duplicate package imports
        
        Strategy: Remove packages that conflict with pdfLaTeX since it's the default compiler
        """
        import re
        
        fixed = False
        
        # Conflict 1: fontspec + inputenc (CRITICAL)
        # fontspec only works with XeLaTeX/LuaLaTeX, inputenc works with pdfLaTeX
        # Since we default to pdfLaTeX, remove fontspec
        if '\\usepackage{fontspec}' in latex_code and '\\usepackage[utf8]{inputenc}' in latex_code:
            latex_code = re.sub(r'\\usepackage\{fontspec\}\s*\n?', '', latex_code)
            print("[FIX] Removed \\usepackage{fontspec} (conflicts with inputenc for pdfLaTeX)")
            fixed = True
        
        # Conflict 2: fontspec alone without inputenc (use inputenc for pdfLaTeX compatibility)
        elif '\\usepackage{fontspec}' in latex_code and '\\usepackage' in latex_code:
            # Replace fontspec with inputenc for better pdfLaTeX compatibility
            latex_code = latex_code.replace(
                '\\usepackage{fontspec}',
                '\\usepackage[utf8]{inputenc}'
            )
            print("[FIX] Replaced \\usepackage{fontspec} with \\usepackage[utf8]{inputenc} for pdfLaTeX")
            fixed = True
        
        # Conflict 3: Remove duplicate package declarations
        lines = latex_code.split('\n')
        seen_packages = set()
        filtered_lines = []
        
        for line in lines:
            # Check if line is a package declaration
            pkg_match = re.match(r'\\usepackage(\[.*?\])?\{(.*?)\}', line.strip())
            if pkg_match:
                pkg_name = pkg_match.group(2)
                pkg_options = pkg_match.group(1) or ''
                pkg_key = f"{pkg_name}{pkg_options}"
                
                if pkg_key in seen_packages:
                    print(f"[FIX] Removed duplicate package: \\usepackage{pkg_options}{{{pkg_name}}}")
                    fixed = True
                    continue
                else:
                    seen_packages.add(pkg_key)
            
            filtered_lines.append(line)
        
        latex_code = '\n'.join(filtered_lines)
        
        if not fixed:
            print("[INFO] No package conflicts detected")
        
        return latex_code
    
    def _ensure_graphicspath(self, latex_code: str, context: Dict[str, Any]) -> str:
        r"""
        Ensure \graphicspath is set correctly (minimal post-processing)
        
        This is the ONE piece of post-processing that makes sense - ensuring
        LaTeX knows where to find the images.
        """
        import re
        
        if not context.get('assets_dir') or not context.get('extracted_images'):
            return latex_code  # No images, no need for graphicspath
        
        # Get assets directory name
        assets_dir_name = os.path.basename(context['assets_dir'])
        
        # Check if \graphicspath is already present
        if '\\graphicspath' not in latex_code:
            # Add it after \usepackage{graphicx}
            graphicspath_line = f"\\graphicspath{{{{./{assets_dir_name}/}}}}\n"
            
            # Try to insert after \usepackage{graphicx}
            if '\\usepackage{graphicx}' in latex_code or '\\usepackage[' in latex_code and 'graphicx' in latex_code:
                # Find the line with graphicx
                lines = latex_code.split('\n')
                new_lines = []
                added = False
                
                for line in lines:
                    new_lines.append(line)
                    if ('\\usepackage{graphicx}' in line or ('\\usepackage[' in line and 'graphicx' in line)) and not added:
                        new_lines.append(graphicspath_line.rstrip())
                        added = True
                
                if added:
                    latex_code = '\n'.join(new_lines)
                    print(f"[INFO] Added \\graphicspath{{{{{assets_dir_name}/}}}}")
            else:
                # graphicx not found, add both after \documentclass
                if '\\documentclass' in latex_code:
                    latex_code = latex_code.replace(
                        '\\documentclass',
                        f'\\documentclass',
                        1
                    )
                    # Find end of documentclass line
                    lines = latex_code.split('\n')
                    new_lines = []
                    for i, line in enumerate(lines):
                        new_lines.append(line)
                        if i == 0 and '\\documentclass' in line:
                            new_lines.append('\\usepackage{graphicx}')
                            new_lines.append(graphicspath_line.rstrip())
                    latex_code = '\n'.join(new_lines)
                    print(f"[INFO] Added \\usepackage{{graphicx}} and \\graphicspath")
        else:
            print("[INFO] \\graphicspath already present in LaTeX")
        
        return latex_code
    
    def _get_system_prompt(self) -> str:
        """System prompt for GPT-4 - defines its role and capabilities"""
        return r"""You are an expert LaTeX reconstructor. Generate LaTeX that is VISUALLY IDENTICAL to the original PDF.

REQUIREMENTS:
1. Complete LaTeX: \\documentclass to \\end{document} with packages (graphicx, amsmath, amssymb, geometry, inputenc, tikz if needed)
2. Include ALL extracted images using \\includegraphics
3. Preserve exact numbering hierarchy and structure
4. Match layout, spacing, fonts, and appearance precisely

CRITICAL RULES:
- Use tabular for header metadata (not \\hfill). Analyze visual alignment: if elements appear on same row in PDF, use same tabular row with proper spacing.
- **NUMBERING CORRECTION**: Ensure sequential numbering is correct. If the original PDF has numbering errors (duplicate numbers, skipped numbers), fix them to be sequential. Use \\setcounter{enumi}{n} to start at the correct number, then each \\item should increment correctly (11, 12, 13, 14... not 11, 11, 12, 13...).
- Preserve hierarchical structure (main → sub → sub-sub parts)
- Use LaTeX commands (\\theta, \\pi) not Unicode
- Don't duplicate text already in images
- Missing content: vector diagrams → \\tikz, charts → LaTeX, figures → \\includegraphics

Output ONLY LaTeX code - no explanations.
"""
            
    # ============================================================================
    # Prompt Generation Methods
    # ============================================================================
    
    def _build_instruction_text(self, context: Dict[str, Any]) -> str:
        """
        Build the main instruction text for the user prompt.
        
        Args:
            context: Context dictionary with document information
            
        Returns:
            Formatted instruction string
        """
        pdf_name = context['pdf_name']
        num_images = len(context['extracted_images'])
        
        instruction = f"""Reconstruct this document as LaTeX that produces VISUALLY IDENTICAL output.

Document: {pdf_name}

PROVIDED DATA:
1. Original PDF pages as images (analyze these carefully)
2. OCR data with text content and positioning
3. Extracted images with filenames and positions
4. Visual content analysis for missing elements

MANDATORY REQUIREMENTS:
- Include ALL {num_images} extracted images using \\includegraphics commands
- Preserve exact hierarchical numbering structure from original (but CORRECT any numbering errors: ensure sequential numbering without duplicates)
- Match visual layout, spacing, and appearance precisely
- Use extracted images in logical positions based on page numbers and bounding boxes

LAYOUT RULES:
- Header information must appear at the TOP of the document
- **CRITICAL - Header Alignment Analysis**: When analyzing headers (Term, Subject, Course Number, etc.):
  * Carefully examine the ORIGINAL PDF VISUALLY to determine if elements are in the SAME ROW or DIFFERENT ROWS
  * Look at horizontal alignment - if "Subject" and "Course Number" are visually aligned horizontally on the same row, use a SINGLE row in tabular
  * Do NOT assume elements are on separate rows just because there's a line break in text/OCR
  * Use visual analysis: If text appears side-by-side visually, put them in the SAME tabular row with appropriate column separators
  * Example: If "Term: Fall 2023" is left-aligned and "Subject: Physics" and "Course Number: 150" are both right-aligned on the SAME visual row, use a SINGLE tabular row: left column = "Term: Fall 2023", right column = "Subject: Physics (PHY) + spacing + Course Number: 150"
- Images should be placed near the questions they relate to
- Tables should be rendered as LaTeX tables, not images
- Maintain proper page breaks and document flow

TABLE HANDLING:
- If you see a SIMPLE data table (rows/columns of text/numbers), recreate it using LaTeX \\begin{{tabular}} or \\begin{{table}}
- Do NOT use \\includegraphics for simple data tables - they should be LaTeX code
- For COMPLEX diagrams, chemical structures, or figures, use \\includegraphics
- Preserve table structure, headers, and data exactly

CRITICAL: You MUST include ALL {num_images} images. Do not skip any images, especially the last ones in the sequence.

Extracted images available:
"""
        
        # List extracted images with context
        for i, img in enumerate(context['extracted_images']):
            instruction += f"- {img['filename']} (page {img['page']}, {img['position_type']}, image {i+1} of {num_images})\n"
        
        # Add assets directory info
        if context.get('assets_dir'):
            assets_dir_name = os.path.basename(context['assets_dir'])
            instruction += f"\n\nIMPORTANT: Use \\graphicspath{{{{./{assets_dir_name}/}}}} to reference images."
        
        # Add PDF analysis instructions
        instruction += self._get_pdf_analysis_instructions()
        
        return instruction
    
    def _get_pdf_analysis_instructions(self) -> str:
        """Get instructions for analyzing PDF pages visually."""
        return """
---\n\nOriginal PDF pages (analyze these visually for layout and structure):
\nIMPORTANT: Use the original PDF pages to understand:
- **Header Layout Analysis**: Where header elements (Term, Subject, Course Number) appear and their HORIZONTAL ALIGNMENT. Look at the PDF visually: if elements are on the same horizontal line, they must be in the same tabular row. Ignore text line breaks - use visual analysis only.
- Where the header (Name, Section, TA) appears
- Which images belong to which questions
- Which content should be tables vs images
- Proper page breaks and document flow

SPECIAL NOTE: Complex visual diagrams, charts, and figures should use \\includegraphics, NOT LaTeX table code.
"""
    
    def _build_final_instruction(self, context: Dict[str, Any]) -> str:
        """
        Build the final instruction text for LaTeX generation.
        
        Args:
            context: Context dictionary with document information
            
        Returns:
            Final instruction string
        """
        num_images = len(context['extracted_images'])
        
        return f"""
---\n\nGenerate complete LaTeX code that recreates this document EXACTLY.\n\nKey points:
- Reference images by filename (e.g., page1_img1.png)
- Use visual analysis for missing content
- Match sizes and layout precisely
- Don't duplicate content
- Output ONLY LaTeX code\n\nCRITICAL: You MUST include the ENTIRE document from start to finish. Do not truncate or cut off any content, especially:
- All parts of all problems (including sub-parts like (d), (e), etc.)
- Grading sections
- Any content that appears on the last pages
- Complete all sections until \\end{{document}}\n\nVERIFICATION: You must include exactly {num_images} \\includegraphics commands. Count them before finalizing your response.\n\nLAYOUT VERIFICATION: Before finalizing, verify that:
- Header appears at the top of the document
- **Header row structure**: Check visually if header elements like \"Subject\" and \"Course Number\" appear on the SAME horizontal line in the original PDF. If yes, they MUST be in the SAME tabular row, not separate rows. Use visual alignment, not text line breaks.
- Images are placed near their related questions
- Simple data tables are rendered as LaTeX code, not images
- Complex diagrams and chemical structures use \\includegraphics
- Document flow matches the original PDF pages
- ALL content from ALL pages is included"""
    
    def _build_user_prompt(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build multimodal user prompt with images and text for GPT-4 Vision.
        
        This method assembles the complete user prompt including:
        - Instruction text with layout rules
        - Original PDF page images
        - OCR data
        - Structured JSON data
        - Visual content analysis
        - Final instructions
        
        Args:
            context: Rich context dictionary with all data sources
            
        Returns:
            List of message content dictionaries for GPT-4 Vision API
        """
        content = []
        
        # Build main instruction text
        instruction = self._build_instruction_text(context)
        content.append({"type": "text", "text": instruction})
        
        # Add original PDF page images
        for page in context['original_pages']:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{page['base64']}",
                    "detail": "high"
                }
            })
        
        # Add OCR data if available
        if context.get('ocr_data'):
            ocr_text = f"\n\n---\n\nOCR Data (text content):\n```json\n{json.dumps(context['ocr_data'], indent=2)[:4000]}\n```"
            content.append({"type": "text", "text": ocr_text})
        
        # Add structured JSON data if available
        if context.get('json_data'):
            json_text = f"\n\n---\n\nStructured JSON Data (COMPLETE questions and sub-questions):\n```json\n{json.dumps(context['json_data'], indent=2)[:6000]}\n```"
            content.append({"type": "text", "text": json_text})
        
        # Add visual content analysis if available
        if context.get('visual_content'):
            visual_analysis = self._build_visual_analysis_text(context['visual_content'])
            content.append({"type": "text", "text": visual_analysis})
        
        # Add final instruction
        final_instruction = self._build_final_instruction(context)
        content.append({"type": "text", "text": final_instruction})
        
        return content
    
    def _build_visual_analysis_text(self, visual_content: Dict[str, Any]) -> str:
        """
        Build visual content analysis text for the prompt.
        
        Args:
            visual_content: Visual content analysis results
            
        Returns:
            Formatted visual analysis text
        """
        summary = visual_content.get('summary', {})
        analysis = f"""
        
        ---
        
        VISUAL CONTENT ANALYSIS:
        Total visual elements detected: {summary.get('total_elements', 0)}
        PyMuPDF extractions: {summary.get('extracted_by_pymupdf', 0)}
        Missing visual content: {summary.get('missed_by_pymupdf', 0)}
        
        Missing visual elements that need LaTeX representation:
        """
        
        for element in visual_content.get('missing_images', []):
            analysis += f"""
        - {element.get('type', 'unknown')}: {element.get('description', 'No description')} (page {element.get('page_number', 'unknown')})
          Suggested approach: {element.get('latex_suggestion', 'No suggestion')}
          Complexity: {element.get('complexity', 'unknown')}
            """
        
        return analysis
    
    def _compile_latex(self, tex_path: str, output_dir: str) -> Optional[str]:
        """
        Compile LaTeX to PDF, auto-detecting Unicode and using appropriate engine.
        
        Automatically selects XeLaTeX for Unicode documents, falls back to pdfLaTeX
        for standard documents. Runs multiple passes to resolve references.
        
        Args:
            tex_path: Path to LaTeX .tex file
            output_dir: Directory where compilation output should be placed
            
        Returns:
            Path to generated PDF file, or None if compilation fails
        """
        # Check if document contains Unicode characters
        try:
            with open(tex_path, 'r', encoding='utf-8') as f:
                content = f.read()
                has_unicode = any(ord(char) > 127 for char in content)
        except:
            has_unicode = False
        
        # Choose appropriate LaTeX engine
        if has_unicode:
            # Try xelatex for Unicode support
            compiler = shutil.which("xelatex")
            if compiler:
                print("[INFO] Unicode detected - using XeLaTeX for compilation")
            else:
                # Fallback to pdflatex
                compiler = shutil.which("pdflatex")
                print("[WARN] Unicode detected but XeLaTeX not found - using pdflatex (may fail)")
        else:
            compiler = shutil.which("pdflatex")
        
        if not compiler:
            print("[WARN] No LaTeX compiler found (tried xelatex and pdflatex)")
            return None
        
        try:
            # Run multiple passes for references and cross-references
            for pass_num in range(self.LATEX_COMPILE_PASSES):
                result = subprocess.run(
                    [compiler, "-interaction=nonstopmode", Path(tex_path).name],
                    cwd=output_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.LATEX_COMPILE_TIMEOUT
                )
                # First pass often has warnings (missing references) which is normal
                if pass_num == 0 and result.returncode != 0:
                    print(f"[WARN] First compilation pass had errors (this is sometimes normal)")
            
            pdf_path = tex_path.replace(".tex", ".pdf")
            if os.path.exists(pdf_path):
                return pdf_path
            else:
                print("[ERROR] PDF file not generated")
                return None
            
        except subprocess.TimeoutExpired:
            print(f"[ERROR] LaTeX compilation timed out ({self.LATEX_COMPILE_TIMEOUT}s)")
            return None
        except Exception as e:
            print(f"[ERROR] LaTeX compilation failed: {e}")
            return None

