"""OCR service using vision-capable LLMs to extract text from PDFs.

This service uses OpenAI's GPT-4 Vision or similar models to perform OCR on PDF pages,
preventing information loss that can occur with traditional PDF parsing libraries like PyPDF2.
"""
from __future__ import annotations

import os
import base64
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF for PDF to image conversion
from PIL import Image
import io

try:
    import openai
except ImportError as exc:
    raise RuntimeError("The 'openai' package is required for OCR functionality.") from exc

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")

if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not set – OCR functionality will be disabled.")


def pdf_to_images(pdf_path: Path, dpi: int = 300) -> List[Image.Image]:
    """Convert PDF pages to PIL Images for OCR processing.
    
    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for image conversion (higher = better quality but slower)
    
    Returns:
        List of PIL Image objects, one per page
    """
    try:
        # Open PDF with PyMuPDF
        pdf_document = fitz.open(str(pdf_path))
        images = []
        
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            
            # Create a transformation matrix for the desired DPI
            mat = fitz.Matrix(dpi/72, dpi/72)  # 72 is the default DPI
            
            # Render page to image
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
        
        pdf_document.close()
        return images
        
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        raise RuntimeError(f"Failed to convert PDF to images: {e}")


def encode_image_to_base64(image: Image.Image) -> str:
    """Convert PIL Image to base64 string for API transmission."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return img_str


def extract_text_from_image_with_llm(image: Image.Image, prompt: str = None) -> str:
    """Extract text from a single image using OpenAI's vision model.
    
    Args:
        image: PIL Image to process
        prompt: Custom prompt for the LLM (optional)
    
    Returns:
        Extracted text from the image
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured for OCR")
    
    # Default prompt optimized for academic document extraction
    default_prompt = """Please extract all text from this image. This appears to be an academic document (quiz, test, or assessment). 

Important guidelines:
1. Extract ALL visible text including questions, answer options, headers, footers, and any other text
2. Preserve the exact formatting and structure as much as possible
3. For multiple choice questions, clearly identify question numbers and option labels (A, B, C, D, etc.)
4. Include any mathematical expressions, symbols, or special characters
5. Maintain line breaks and paragraph structure
6. If there are tables, extract them in a readable format
7. Include page numbers if present
8. Do not add any interpretation or commentary - just extract the raw text

Please provide the extracted text in a clean, readable format."""

    user_prompt = prompt or default_prompt
    
    try:
        # Convert image to base64
        base64_image = encode_image_to_base64(image)
        
        # Prepare the API call
        if hasattr(openai, 'OpenAI'):
            # Use new OpenAI client (>=1.0)
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=OPENAI_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4000,
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        else:
            # Fallback to legacy client
            response = openai.ChatCompletion.create(
                model=OPENAI_VISION_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=4000,
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
            
    except Exception as e:
        logger.error(f"Error extracting text from image with LLM: {e}")
        raise RuntimeError(f"LLM OCR failed: {e}")


def extract_text_from_pdf_with_ocr(pdf_path: Path, prompt: str = None) -> str:
    """Extract text from PDF using OCR with vision-capable LLM.
    
    Args:
        pdf_path: Path to the PDF file
        prompt: Custom prompt for the LLM (optional)
    
    Returns:
        Extracted text from all pages concatenated
    """
    logger.info(f"Starting OCR extraction from PDF: {pdf_path}")
    
    try:
        # Convert PDF to images
        images = pdf_to_images(pdf_path)
        logger.info(f"Converted PDF to {len(images)} images")
        
        # Extract text from each page
        all_text = []
        for i, image in enumerate(images):
            logger.info(f"Processing page {i+1}/{len(images)}")
            page_text = extract_text_from_image_with_llm(image, prompt)
            all_text.append(page_text)
            
            # Add page separator for multi-page documents
            if len(images) > 1:
                all_text.append(f"\n--- Page {i+1} ---\n")
        
        full_text = "\n".join(all_text)
        logger.info(f"OCR extraction completed. Total text length: {len(full_text)} characters")
        
        return full_text
        
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        raise RuntimeError(f"Failed to extract text from PDF using OCR: {e}")


def extract_questions_from_pdf_with_ocr(pdf_path: Path) -> Dict[str, Any]:
    """Extract questions from PDF using OCR and LLM-based parsing.
    
    This function combines OCR extraction with intelligent parsing to identify
    questions, options, and structure in academic documents.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        Dictionary containing extracted title and questions
    """
    logger.info(f"Starting OCR-based question extraction from: {pdf_path}")
    
    # Extract raw text using OCR
    raw_text = extract_text_from_pdf_with_ocr(pdf_path)
    
    # Use LLM to parse the extracted text into structured questions
    parsing_prompt = f"""Please analyze the following text extracted from an academic document and parse it into structured questions.

Extracted text:
{raw_text}

Please parse this text and return a JSON object with the following structure:
1) If it's a multiple choice question, return a JSON object with the following structure:
{{
    "title": "Document title or header",
    "questions": [
        {{
            "q_number": "1",  # Can be "1", "1a", "1b", "2", etc. for sub-questions
            "stem_text": "The question text/stem",
            "options": {{
                "A": "Option A text",
                "B": "Option B text", 
                "C": "Option C text",
                "D": "Option D text"
            }}
        }}
    ]
}}
2) If it's a True/False question, return a JSON object with the following structure:
{{
    "title": "Document title or header",
    "questions": [
        {{
            "q_number": "1",  # Can be "1", "1a", "1b", "2", etc. for sub-questions
            "stem_text": "The question text/stem",
            "options": {{
                "True": "True",
                "False": "False"
            }}
        }}
    ]
}}
3) If it's a short answer question, return a JSON object with the following structure:
{{  
    "title": "Document title or header",
    "questions": [
        {{
            "q_number": "1",  # Can be "1", "1a", "1b", "2", etc. for sub-questions
            "stem_text": "The question text/stem",
            "blank_to_fill": "The blank to be filled in"
        }}
    ]
}}

Guidelines:
1. Identify the document title (usually at the top)
2. Look for any general instructions or guidelines at the beginning
3. Find all multiple choice questions
4. Find all True/False questions
5. Find all short answer questions
6. Extract question numbers, stems, and all answer options
7. Handle various question formats (Q1, Question 1, 1., 1a, 1b, 1i, 1ii, etc.)
8. For sub-questions, use the exact format (e.g., "1a", "1b", "1i", "1ii", etc.)
9. Preserve the exact text of questions and options
10. If a question has fewer than 4 options, only include the ones present
11. If the text doesn't contain questions, return empty questions array
12. Ensure the JSON is valid and properly formatted
13. Question numbers should be strings to handle sub-questions properly
14. Pay attention to any specific instructions for different question types

Return only the JSON object, no additional text."""

    try:
        # Use OpenAI to parse the extracted text
        if hasattr(openai, 'OpenAI'):
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Use text model for parsing
                messages=[
                    {"role": "user", "content": parsing_prompt}
                ],
                max_tokens=4000,
                temperature=0.1
            )
            parsed_result = response.choices[0].message.content.strip()
        else:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": parsing_prompt}
                ],
                max_tokens=4000,
                temperature=0.1
            )
            parsed_result = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        import json
        try:
            # Try to extract JSON if it's wrapped in markdown code blocks
            if "```json" in parsed_result:
                json_start = parsed_result.find("```json") + 7
                json_end = parsed_result.find("```", json_start)
                parsed_result = parsed_result[json_start:json_end].strip()
            elif "```" in parsed_result:
                json_start = parsed_result.find("```") + 3
                json_end = parsed_result.find("```", json_start)
                parsed_result = parsed_result[json_start:json_end].strip()
            
            result = json.loads(parsed_result)
            logger.info(f"Successfully parsed {len(result.get('questions', []))} questions using OCR")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response: {parsed_result}")
            raise RuntimeError(f"Failed to parse OCR results: {e}")
            
    except Exception as e:
        logger.error(f"OCR-based question extraction failed: {e}")
        raise RuntimeError(f"Failed to extract questions using OCR: {e}")


def extract_answers_from_pdf_with_ocr(pdf_path: Path) -> Dict[str, tuple[str, str]]:
    """Extract answer key from PDF using OCR.
    
    Args:
        pdf_path: Path to the PDF file
    
    Returns:
        Dictionary mapping question number (string) to (correct_option, reason)
    """
    logger.info(f"Starting OCR-based answer extraction from: {pdf_path}")
    
    # Extract raw text using OCR
    raw_text = extract_text_from_pdf_with_ocr(pdf_path)
    
    # Use LLM to parse answers
    parsing_prompt = f"""Please analyze the following text extracted from an answer key document and parse it into structured answers.

Extracted text:
{raw_text}

Please parse this text and return a JSON object mapping question numbers to answers:
{{
    "1": ["A", "Explanation for why A is correct"],
    "1a": ["B", "Explanation for why B is correct"],
    "1b": ["C", "Explanation for why C is correct"],
    "2": ["D", "Explanation for why D is correct"],
    ...
}}

Guidelines:
1. Look for question numbers followed by answer options (A, B, C, D)
2. Handle sub-questions like "1a", "1b", "2a", etc.
3. Extract both the correct option letter and any explanation/reasoning
4. Handle various formats: "1. A", "Question 1: B", "1a) C - explanation", etc.
5. If no explanation is provided, use empty string
6. Question numbers should be strings to handle sub-questions properly
7. Return only the JSON object, no additional text

Return only the JSON object, no additional text."""

    try:
        # Use OpenAI to parse the extracted text
        if hasattr(openai, 'OpenAI'):
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": parsing_prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )
            parsed_result = response.choices[0].message.content.strip()
        else:
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": parsing_prompt}
                ],
                max_tokens=2000,
                temperature=0.1
            )
            parsed_result = response.choices[0].message.content.strip()
        
        # Parse the JSON response
        import json
        try:
            # Try to extract JSON if it's wrapped in markdown code blocks
            if "```json" in parsed_result:
                json_start = parsed_result.find("```json") + 7
                json_end = parsed_result.find("```", json_start)
                parsed_result = parsed_result[json_start:json_end].strip()
            elif "```" in parsed_result:
                json_start = parsed_result.find("```") + 3
                json_end = parsed_result.find("```", json_start)
                parsed_result = parsed_result[json_start:json_end].strip()
            
            result = json.loads(parsed_result)
            
            # Convert string keys to integers and tuples
            answers = {}
            for q_num_str, answer_data in result.items():
                try:
                    q_num = int(q_num_str)
                    if isinstance(answer_data, list) and len(answer_data) >= 2:
                        answers[q_num] = (answer_data[0], answer_data[1])
                    elif isinstance(answer_data, str):
                        answers[q_num] = (answer_data, "")
                except ValueError:
                    continue
            
            logger.info(f"Successfully parsed {len(answers)} answers using OCR")
            return answers
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Raw response: {parsed_result}")
            raise RuntimeError(f"Failed to parse OCR answer results: {e}")
            
    except Exception as e:
        logger.error(f"OCR-based answer extraction failed: {e}")
        raise RuntimeError(f"Failed to extract answers using OCR: {e}") 