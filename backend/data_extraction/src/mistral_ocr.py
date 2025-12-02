"""
Mistral OCR extractor using Pixtral vision model
Handles scanned PDFs and documents with poor text extraction quality
"""
import base64
import time
from typing import List, Tuple, Dict, Optional
from mistralai import Mistral
from config import (
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
    MISTRAL_MAX_TOKENS,
    MISTRAL_TEMPERATURE,
    MISTRAL_OCR_PROMPT
)


class MistralOCRExtractor:
    """Extract text from images using Mistral's Pixtral vision model"""
    
    def __init__(self):
        """
        Initialize Mistral OCR extractor
        API key is loaded from .env file via MISTRAL_API_KEY environment variable
        """
        self.api_key = MISTRAL_API_KEY
        if not self.api_key or self.api_key == "your-api-key-here":
            raise ValueError(
                "Mistral API key not found. Please:\n"
                "1. Create a .env file in the project root\n"
                "2. Add MISTRAL_API_KEY=your-api-key-here to the .env file\n"
                "3. Make sure python-dotenv is installed"
            )
        
        # Initialize Mistral client
        self.client = Mistral(api_key=self.api_key)
        self.model = MISTRAL_MODEL
        self.max_tokens = MISTRAL_MAX_TOKENS
        self.temperature = MISTRAL_TEMPERATURE
    
    def extract_text_from_pages(
        self, 
        page_images: List[Tuple[int, bytes]]
    ) -> Dict[int, str]:
        """
        Extract text from page images using Mistral OCR
        
        Args:
            page_images: List of (page_number, image_bytes) tuples
            
        Returns:
            Dictionary mapping page_number -> extracted_text
        """
        if not page_images:
            print("[WARN] No page images provided for Mistral OCR")
            return {}
        
        results = {}
        total_pages = len(page_images)
        
        print(f"[MISTRAL OCR] Processing {total_pages} page(s)...")
        
        for idx, (page_num, img_bytes) in enumerate(page_images, 1):
            try:
                # Encode image to base64
                img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                
                # Prepare messages for Mistral API
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": MISTRAL_OCR_PROMPT
                            },
                            {
                                "type": "image_url",
                                "image_url": f"data:image/png;base64,{img_base64}"
                            }
                        ]
                    }
                ]
                
                # Call Mistral API
                response = self.client.chat.complete(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature
                )
                
                # Extract text from response
                extracted_text = response.choices[0].message.content
                results[page_num] = extracted_text
                
                print(f"[MISTRAL OCR] Page {page_num}/{total_pages} completed ({len(extracted_text)} chars)")
                
                # Small delay to avoid rate limiting
                if idx < total_pages:
                    time.sleep(0.5)
                
            except Exception as e:
                error_msg = str(e)
                
                # Handle rate limiting
                if "rate_limit" in error_msg.lower() or "429" in error_msg:
                    print(f"[WARN] Rate limit hit on page {page_num}, waiting 60 seconds...")
                    time.sleep(60)
                    # Retry this page
                    try:
                        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                        messages = [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": MISTRAL_OCR_PROMPT},
                                    {"type": "image_url", "image_url": f"data:image/png;base64,{img_base64}"}
                                ]
                            }
                        ]
                        response = self.client.chat.complete(
                            model=self.model,
                            messages=messages,
                            max_tokens=self.max_tokens,
                            temperature=self.temperature
                        )
                        extracted_text = response.choices[0].message.content
                        results[page_num] = extracted_text
                        print(f"[MISTRAL OCR] Page {page_num} completed after retry")
                    except Exception as retry_error:
                        print(f"[ERROR] Mistral OCR failed for page {page_num} after retry: {retry_error}")
                        results[page_num] = ""
                else:
                    print(f"[ERROR] Mistral OCR failed for page {page_num}: {e}")
                    results[page_num] = ""
        
        return results
    
    def extract_text_from_document(self, page_images: List[Tuple[int, bytes]]) -> Dict[str, any]:
        """
        Extract text from entire document (all pages)
        Returns in same format as DocumentReader for compatibility
        
        Args:
            page_images: List of (page_number, image_bytes) tuples
            
        Returns:
            Dictionary with text, pages, number_of_pages, metadata
        """
        page_texts = self.extract_text_from_pages(page_images)
        
        # Build result in same format as PyMuPDF reader
        result = {
            "text": "",
            "pages": [],
            "number_of_pages": len(page_texts),
            "metadata": {},
            "has_images": False,
            "extraction_method": "Mistral OCR"
        }
        
        # Combine all pages
        for page_num in sorted(page_texts.keys()):
            page_text = page_texts[page_num]
            
            result["pages"].append({
                "page_number": page_num,
                "text": page_text
            })
            
            result["text"] += f"\n--- Page {page_num} ---\n{page_text}"
        
        print(f"[MISTRAL OCR] Extraction complete: {len(result['text'])} total characters")
        
        return result

