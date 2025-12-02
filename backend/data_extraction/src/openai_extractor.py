"""
OpenAI GPT-4 Vision multimodal extractor for question papers with granular extraction

Uses hybrid approach: text extraction + embedded image analysis + positioning merger
API key is automatically loaded from .env file via config.py
Make sure you have a .env file with OPENAI_API_KEY set
"""
import json
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from openai import OpenAI
from config import (
    OPENAI_API_KEY, 
    OPENAI_MODEL, 
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE,
    EXTRACTION_PROMPT,
    QUESTIONS_PER_CHUNK
)
from .positioning_extractor import merge_positioning_with_structure


class OpenAIExtractor:
    """Extract questions using OpenAI GPT-5 with multimodal capabilities"""
    
    def __init__(self, api_key: str = None):
        # Load API key from .env file (via config.py) or use provided key
        self.api_key = api_key or OPENAI_API_KEY
        if not self.api_key or self.api_key == "your-api-key-here":
            raise ValueError(
                "OpenAI API key not provided. Please:\n"
                "1. Copy env.template to .env\n"
                "2. Add your API key to the .env file\n"
                "3. Or set OPENAI_API_KEY environment variable"
            )
        
        # Initialize OpenAI client (v1.0+ API)
        self.client = OpenAI(api_key=self.api_key)
        self.model = OPENAI_MODEL
        self.max_tokens = OPENAI_MAX_TOKENS
        self.temperature = OPENAI_TEMPERATURE
    
    def extract_from_text_and_images(
        self,
        text: str,
        images: List[Tuple[int, str, str]],
        document_name: str,
        metadata: Dict = None,
        pdf_path: str = None
    ) -> Optional[Dict]:
        """
        Extract questions using hybrid approach: text + embedded images + positioning
        This is the PRIMARY extraction method using GPT-4 Vision's multimodal capabilities
        
        Args:
            text: Full extracted text from document
            images: List of (page_number, base64_image, context) tuples
            document_name: Name of the document
            metadata: Optional document metadata
            pdf_path: Path to PDF file for positioning extraction
            
        Returns:
            Extracted data with positioning as dictionary or None if extraction fails
        """
        if not text or len(text.strip()) < 50:
            print("[WARN] Text too short for extraction")
            return None
        
        try:
            # Truncate text if too long
            max_chars = 50000  # GPT-4 Omni has large context window
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... [truncated]"
            
            # Prepare user content with text
            user_content = [
                {
                    "type": "text",
                    "text": f"Document: {document_name}\n\nFull text content:\n{text}"
                }
            ]
            
            # Add embedded images if available
            if images:
                user_content.append({
                    "type": "text",
                    "text": f"\n\nThe document contains {len(images)} embedded image(s) (diagrams, figures, charts):"
                })
                
                for idx, (page_num, img_base64, context) in enumerate(images[:10], 1):
                    # Add context for each image
                    user_content.append({
                        "type": "text",
                        "text": f"\nImage {idx} (Page {page_num}): {context}"
                    })
                    
                    # Add the image
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}",
                            "detail": "high"
                        }
                    })
                
                print(f"[OPENAI] Sending text + {len(images[:10])} embedded images to {self.model}...")
            else:
                print(f"[OPENAI] Sending text-only to {self.model}...")
            
            messages = [
                {
                    "role": "system",
                    "content": EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": user_content
                }
            ]
            
            # Make API call (OpenAI v1.0+ syntax)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Try to parse as JSON
            try:
                # Remove markdown formatting if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                data = json.loads(content.strip())
                print("[OK] Successfully extracted structured data from GPT-4 Vision")
                
                # Merge with positioning data if PDF path is provided
                if pdf_path and Path(pdf_path).exists():
                    print("[POSITIONING] Merging positioning data from PyMuPDF...")
                    data["extraction_method"] = "gpt4_vision_with_pymupdf_positioning"
                    data = merge_positioning_with_structure(data, pdf_path)
                    print("[OK] Positioning data merged successfully")
                else:
                    data["extraction_method"] = "gpt4_vision_only"
                    print("[WARN] No PDF path provided, skipping positioning extraction")
                
                return data
                
            except json.JSONDecodeError as e:
                print(f"[ERROR] Failed to parse OpenAI response as JSON: {e}")
                print(f"Response content: {content[:500]}...")
                return None
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for rate limit errors
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("[WARN] Rate limit exceeded. Waiting 60 seconds...")
                time.sleep(60)
                return self.extract_from_text_and_images(text, images, document_name, metadata, pdf_path)
            
            # Check for invalid request errors
            elif "invalid" in error_msg.lower() or "400" in error_msg:
                print(f"[ERROR] Invalid request to OpenAI: {e}")
                return None
            
            # All other errors
            else:
                print(f"[ERROR] OpenAI extraction failed: {e}")
                return None
    
    def extract_from_images(
        self, 
        images: List[Tuple[int, str]], 
        document_name: str
    ) -> Optional[Dict]:
        """
        Extract questions from document images using GPT-4 Vision
        
        Args:
            images: List of (page_number, base64_image) tuples
            document_name: Name of the document
            
        Returns:
            Extracted data as dictionary or None if extraction fails
        """
        if not images:
            print("No images provided for extraction")
            return None
        
        try:
            # Prepare messages with images
            messages = [
                {
                    "role": "system",
                    "content": EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Extract all questions from this document: {document_name}"
                        }
                    ]
                }
            ]
            
            # Add images to the message (limit to first 10 pages to avoid token limits)
            for page_num, img_base64 in images[:10]:
                messages[1]["content"].append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_base64}",
                        "detail": "high"
                    }
                })
            
            print(f"Sending {len(images[:10])} pages to OpenAI GPT-4 Vision...")
            
            # Make API call (OpenAI v1.0+ syntax)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Try to parse as JSON
            try:
                # Remove markdown formatting if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                data = json.loads(content.strip())
                print("Successfully extracted data using OpenAI")
                return data
                
            except json.JSONDecodeError as e:
                print(f"Failed to parse OpenAI response as JSON: {e}")
                print(f"Response content: {content[:500]}...")
                return None
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for rate limit errors
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("Rate limit exceeded. Waiting 60 seconds...")
                time.sleep(60)
                return self.extract_from_images(images, document_name)
            
            # Check for invalid request errors
            elif "invalid" in error_msg.lower() or "400" in error_msg:
                print(f"Invalid request to OpenAI: {e}")
                return None
            
            # All other errors
            else:
                print(f"OpenAI extraction failed: {e}")
                return None
    
    def extract_from_text(
        self, 
        text: str, 
        document_name: str,
        metadata: Dict = None
    ) -> Optional[Dict]:
        """
        Extract questions from text using GPT-4 (text-only)
        Fallback when images are not available
        
        Args:
            text: Document text content
            document_name: Name of the document
            metadata: Optional document metadata
            
        Returns:
            Extracted data as dictionary or None if extraction fails
        """
        if not text or len(text.strip()) < 50:
            print("Text too short for extraction")
            return None
        
        try:
            # Truncate text if too long (GPT-4 has context limits)
            max_chars = 30000  # Roughly 7500 tokens
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... [truncated]"
            
            messages = [
                {
                    "role": "system",
                    "content": EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Extract all questions from this document:\n\nDocument: {document_name}\n\n{text}"
                }
            ]
            
            print(f"Sending text ({len(text)} chars) to OpenAI GPT-4...")
            
            # Use standard GPT-4 for text extraction (OpenAI v1.0+ syntax)
            response = self.client.chat.completions.create(
                model="gpt-4",  # Use text-only model
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON
            try:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                data = json.loads(content.strip())
                print("Successfully extracted data using OpenAI (text mode)")
                return data
                
            except json.JSONDecodeError as e:
                print(f"Failed to parse OpenAI response as JSON: {e}")
                return None
                
        except Exception as e:
            error_msg = str(e)
            
            # Check for rate limit errors
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("Rate limit exceeded. Waiting 60 seconds...")
                time.sleep(60)
                return self.extract_from_text(text, document_name, metadata)
            
            # All other errors
            else:
                print(f"OpenAI text extraction failed: {e}")
                return None
    
    def _calculate_question_ranges(
        self, 
        total_questions: int, 
        questions_per_chunk: int
    ) -> List[Tuple[int, int]]:
        """
        Calculate question number ranges for each chunk.
        
        Instead of splitting text, we let GPT extract specific question ranges
        from the full document. This ensures no question is ever split mid-way.
        
        Args:
            total_questions: Total number of questions in document (from LLM count)
            questions_per_chunk: Target questions per chunk
            
        Returns:
            List of (start_question, end_question) tuples
            Example: [(1, 5), (6, 10), (11, 15)] for 15 questions, 5 per chunk
        """
        ranges = []
        current_start = 1
        
        while current_start <= total_questions:
            current_end = min(current_start + questions_per_chunk - 1, total_questions)
            ranges.append((current_start, current_end))
            current_start = current_end + 1
        
        return ranges
    
    def extract_with_chunking(
        self,
        text: str,
        images: List[Tuple[int, str, str]],
        document_name: str,
        metadata: Dict = None,
        pdf_path: str = None,
        questions_per_chunk: int = QUESTIONS_PER_CHUNK
    ) -> Optional[Dict]:
        """
        Extract questions using GPT-controlled boundary-safe chunking for large documents.
        
        STRATEGY (v4.1.3):
        - Uses LLM to count total questions (including sub-questions)
        - Calculates question ranges (e.g., Q1-5, Q6-10, Q11-15)
        - Passes FULL TEXT to GPT for each chunk
        - GPT extracts only the specified question range
        - This prevents questions from being split mid-way (GPT understands boundaries)
        
        Example: Document with 30 questions, 5 questions per chunk
        - Chunk 1: Extract Q1-5 from full text
        - Chunk 2: Extract Q6-10 from full text
        - Chunk 3: Extract Q11-15 from full text
        - etc.
        
        Args:
            text: Full extracted text from document
            images: List of (page_number, base64_image, context) tuples
            document_name: Name of the document
            metadata: Optional document metadata (must contain 'estimated_questions')
            pdf_path: Path to PDF file for positioning extraction
            questions_per_chunk: Number of questions per chunk (default from config)
            
        Returns:
            Merged extracted data with positioning as dictionary or None if extraction fails
        """
        if not text or len(text.strip()) < 50:
            print("[WARN] Text too short for extraction")
            return None
        
        try:
            # Calculate question count first (needed to determine chunking strategy)
            print(f"[CHUNKING] Estimating question count...")
            temp_metadata = self._extract_document_metadata(text, document_name)
            total_questions = temp_metadata.get('estimated_questions', 0)
            
            if total_questions == 0:
                print(f"[WARN] Could not estimate question count, using single extraction")
                return self.extract_from_text_and_images(text, images, document_name, metadata, pdf_path)
            
            # Calculate question ranges
            question_ranges = self._calculate_question_ranges(total_questions, questions_per_chunk)
            num_chunks = len(question_ranges)
            
            if num_chunks == 1:
                print(f"[CHUNKING] Document small enough ({total_questions} questions) for single extraction")
                return self.extract_from_text_and_images(text, images, document_name, metadata, pdf_path)
            
            # Skip chunking if <= 2 chunks (faster to do single extraction)
            if num_chunks <= 2:
                print(f"[CHUNKING] Document has only {num_chunks} chunk(s) - using single extraction for speed")
                return self.extract_from_text_and_images(text, images, document_name, metadata, pdf_path)
            
            print(f"[CHUNKING] Document has ~{total_questions} questions - splitting into {num_chunks} chunks ({questions_per_chunk} questions per chunk)...")
            print(f"[CHUNKING] Processing chunks in parallel (max 5 concurrent workers)...")
            
            # Parallelize first chunk extraction (metadata already extracted above)
            all_questions = []
            chunk_results = {}
            doc_metadata = temp_metadata  # Reuse metadata from initial extraction
            
            # Get first chunk info
            first_chunk_info = question_ranges[0]
            first_chunk_idx, (first_start_q, first_end_q) = 1, first_chunk_info
            
            # Remaining chunks (if any)
            remaining_ranges = question_ranges[1:] if len(question_ranges) > 1 else []
            
            with ThreadPoolExecutor(max_workers=5) as executor:
                # Submit first chunk immediately (metadata already done)
                print(f"[CHUNKING] Processing first chunk...")
                first_chunk_future = executor.submit(
                    self._extract_chunk_by_range,
                    text,
                    images,
                    document_name,
                    first_start_q,
                    first_end_q,
                    first_chunk_idx,
                    num_chunks
                )
                
                # Wait for first chunk
                try:
                    first_chunk_result = first_chunk_future.result()
                    if first_chunk_result and first_chunk_result.get('questions'):
                        questions_extracted = len(first_chunk_result['questions'])
                        print(f"[CHUNKING] Chunk {first_chunk_idx}/{num_chunks} (Q{first_start_q}-{first_end_q}): Extracted {questions_extracted} questions")
                        chunk_results[first_chunk_idx] = first_chunk_result
                    else:
                        print(f"[WARN] Chunk {first_chunk_idx}/{num_chunks} (Q{first_start_q}-{first_end_q}): No questions extracted")
                        chunk_results[first_chunk_idx] = None
                except Exception as e:
                    print(f"[ERROR] Chunk {first_chunk_idx}/{num_chunks} (Q{first_start_q}-{first_end_q}) failed: {e}")
                    chunk_results[first_chunk_idx] = None
                
                # Submit remaining chunks
                if remaining_ranges:
                    remaining_futures = {
                        executor.submit(
                            self._extract_chunk_by_range,
                            text,
                            images,
                            document_name,
                            start_q,
                            end_q,
                            chunk_idx,
                            num_chunks
                        ): (chunk_idx, start_q, end_q)
                        for chunk_idx, (start_q, end_q) in enumerate(remaining_ranges, 2)
                    }
                    
                    # Collect remaining results
                    for future in as_completed(remaining_futures):
                        chunk_idx, start_q, end_q = remaining_futures[future]
                        try:
                            chunk_result = future.result()
                            
                            if chunk_result and chunk_result.get('questions'):
                                questions_extracted = len(chunk_result['questions'])
                                print(f"[CHUNKING] Chunk {chunk_idx}/{num_chunks} (Q{start_q}-{end_q}): Extracted {questions_extracted} questions")
                                chunk_results[chunk_idx] = chunk_result
                            else:
                                print(f"[WARN] Chunk {chunk_idx}/{num_chunks} (Q{start_q}-{end_q}): No questions extracted")
                                chunk_results[chunk_idx] = None
                        except Exception as e:
                            print(f"[ERROR] Chunk {chunk_idx}/{num_chunks} (Q{start_q}-{end_q}) failed: {e}")
                            chunk_results[chunk_idx] = None
            
            # Merge results in order
            for chunk_idx in sorted(chunk_results.keys()):
                chunk_result = chunk_results[chunk_idx]
                if chunk_result and chunk_result.get('questions'):
                    all_questions.extend(chunk_result['questions'])
            
            if not all_questions:
                print("[ERROR] No questions extracted from any chunk")
                return None
            
            # Merge all questions into final result
            print(f"\n[CHUNKING] Merging results: {len(all_questions)} total questions")
            
            final_result = {
                **doc_metadata,
                "total_questions": str(len(all_questions)),
                "questions": all_questions,
                "extraction_method": "gpt4_vision_chunked_boundary_safe"
            }
            
            # Apply positioning data if PDF provided
            if pdf_path and Path(pdf_path).exists():
                print("[POSITIONING] Merging positioning data from PyMuPDF...")
                final_result = merge_positioning_with_structure(final_result, pdf_path)
                final_result["extraction_method"] = "gpt4_vision_chunked_boundary_safe_with_pymupdf_positioning"
                print("[OK] Positioning data merged successfully")
            
            return final_result
            
        except Exception as e:
            print(f"[ERROR] Chunked extraction failed: {e}")
            print("[INFO] Falling back to single extraction...")
            # Fallback to regular extraction
            return self.extract_from_text_and_images(text, images, document_name, metadata, pdf_path)
    
    def _extract_document_metadata(self, text: str, document_name: str) -> Dict:
        """
        Extract document-level metadata (institution, domain, topic, etc.)
        
        Args:
            text: Full document text (truncated if needed)
            document_name: Name of the document
            
        Returns:
            Dictionary with document metadata
        """
        # Use full text for metadata extraction (only truncate for very large documents >50K chars)
        # This ensures we capture all question sections, even if they're later in the document
        if len(text) > 50000:
            # For very large documents, use smart truncation: keep beginning and end
            half = 25000
            text_sample = text[:half] + "\n\n... [middle section truncated for metadata extraction] ...\n\n" + text[-half:]
        else:
            text_sample = text
        
        metadata_prompt = f"""Analyze this document and extract ONLY the following metadata.
Return as JSON with these exact fields:

{{
  "document_name": "string",
  "institution_name": "string",
  "domain": "string (Physics, Mathematics, Computer Science, etc.)",
  "topic": "string (specific topic within domain)",
  "number_of_pages": "string",
  "estimated_questions": integer
}}

IMPORTANT for estimated_questions:
- Documents may have MULTIPLE question sections (e.g., Multiple Choice, True/False, Short Answer, Essay)
- Each section may RESTART numbering (e.g., "1. True or False..." after "8. Multiple Choice...")
- Count ALL questions across ALL sections
- Main question with parts a, b, c = count as 4 items (1 main + 3 sub)
- Include all multi-part questions, sections, and sub-parts
- MCQ options (A, B, C, D) are NOT separate questions
- Example 1: "Question 1: Answer the following: a) Explain... b) Describe..." = 3 items
- Example 2: "MCQ section with questions 1-8, then True/False section with questions 1-12" = 20 total questions
- If you see "Multiple Choice (16 marks)" with questions 1-8, and "True / False (24 marks)" with questions 1-12, total is 20 questions
- Return only the number as integer

Document: {document_name}
Text sample:
{text_sample}

Return ONLY the JSON, no other text."""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a document metadata extractor. Return only valid JSON."},
                    {"role": "user", "content": metadata_prompt}
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            metadata = json.loads(content)
            return metadata
            
        except Exception as e:
            print(f"[WARN] Metadata extraction failed: {e}")
            # Return defaults
            return {
                "document_name": document_name,
                "institution_name": "Not provided",
                "domain": "General",
                "topic": "General",
                "number_of_pages": "Unknown"
            }
    
    def _extract_chunk_by_range(
        self,
        full_text: str,
        images: List[Tuple[int, str, str]],
        document_name: str,
        start_question: int,
        end_question: int,
        chunk_number: int,
        total_chunks: int
    ) -> Optional[Dict]:
        """
        Extract a specific range of questions from full document text.
        
        GPT-CONTROLLED BOUNDARY DETECTION (v4.1.3):
        - Receives FULL document text (not pre-split)
        - GPT determines where questions start/end
        - Extracts only the specified question range
        - Guarantees no question is ever split mid-way
        
        Args:
            full_text: Complete document text (not chunked!)
            images: Embedded images
            document_name: Document name
            start_question: First question number to extract (inclusive)
            end_question: Last question number to extract (inclusive)
            chunk_number: Current chunk number (for logging)
            total_chunks: Total number of chunks (for logging)
            
        Returns:
            Extracted data for this question range
        """
        # Prompt GPT to extract specific question range from full text
        range_prompt = f"""Extract ONLY questions {start_question} through {end_question} from this document.

IMPORTANT INSTRUCTIONS:
- Start from question #{start_question}
- End at question #{end_question} 
- Include ALL sub-parts for questions in this range (e.g., if Q5 has parts a, b, c - include them all)
- Do NOT extract questions outside this range
- MCQ options (A, B, C, D) are part of the question, not separate questions
- Use the full granular schema for each question

## HANDLING MULTIPLE QUESTION SECTIONS:
- Documents may have MULTIPLE sections (e.g., Multiple Choice, True/False, Short Answer) with RESTARTED numbering
- Questions may restart at "1" in each section (e.g., "1. True or False..." after "8. Multiple Choice...")
- Extract questions from ALL sections that fall within the specified range
- If asked for questions 9-15 and document has MCQ section (questions 1-8) followed by True/False section (questions 1-12):
  - Questions 9-15 correspond to True/False questions 1-7 (the first 7 True/False questions)
  - Extract those True/False questions 1-7 and number them sequentially as 9-15
- Maintain sequential numbering across all sections: if MCQ has 1-8 and True/False has 1-12, number them as 1-8 and 9-20 respectively

Return a JSON object with this structure:
{{
  "questions": [/* array of question objects for questions {start_question}-{end_question} */]
}}

For each question, extract ALL fields from the granular schema (question_number, question_type, stem_text, options, sub_questions, gold_answer, gold_confidence, answer_explanation, positioning, formulas, visual_elements, tables, code_snippets, key_terms, numerical_values, metadata, confidence, extraction_quality, original_text, page_number, source_page).

IMPORTANT: 
- Use null for non-applicable fields (not empty strings)
- Extract every detail for each question in range {start_question}-{end_question}
- Questions may be in multiple sections with restarted numbering - extract from ALL relevant sections
- Return ONLY valid JSON, no markdown or additional text

Document: {document_name}
Extracting: Questions {start_question}-{end_question} (Chunk {chunk_number}/{total_chunks})

Full document text:
{full_text}"""
        
        try:
            # Truncate if needed (but keep as much as possible)
            max_chars = 60000  # Increased limit since we're not pre-splitting
            if len(full_text) > max_chars:
                # Try to keep beginning and end
                half = max_chars // 2
                full_text = full_text[:half] + "\n\n... [middle section truncated] ...\n\n" + full_text[-half:]
            
            # Build messages
            user_content = [{"type": "text", "text": range_prompt}]
            
            # Add relevant images (limit to reduce token usage)
            if images:
                # Prioritize images from pages likely to contain these questions
                for idx, (page_num, img_base64, context) in enumerate(images[:5], 1):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}",
                            "detail": "high"
                        }
                    })
            
            messages = [
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": user_content}
            ]
            
            # Make API call with reduced token limit for chunking (10000 tokens)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=10000,  # Reduced from 16000 for faster chunk processing
                temperature=self.temperature
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            data = json.loads(content.strip())
            return data
            
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse chunk {chunk_number} (Q{start_question}-{end_question}) response as JSON: {e}")
            return None
        except Exception as e:
            print(f"[ERROR] Chunk {chunk_number} (Q{start_question}-{end_question}) extraction failed: {e}")
            return None

