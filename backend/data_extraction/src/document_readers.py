"""
Document readers for PDF, DOCX, and TXT files
Using PyMuPDF (fitz) for efficient PDF text and image extraction
"""
import io
from pathlib import Path
from typing import Dict, List, Tuple
import base64
import re

try:
    import fitz  # PyMuPDF
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


def is_text_quality_good(text: str) -> bool:
    """
    Check if extracted text quality is sufficient for processing
    
    Args:
        text: Extracted text from document
        
    Returns:
        True if text quality is good, False if OCR is needed
    """
    if not text or len(text.strip()) < 50:
        return False  # Too little text
    
    # Count alphanumeric vs special characters
    alphanumeric = sum(c.isalnum() or c.isspace() for c in text)
    total_chars = len(text)
    
    if total_chars == 0:
        return False
    
    # Good text should have at least 70% alphanumeric/space characters
    ratio = alphanumeric / total_chars
    if ratio < 0.7:
        return False  # Too many special characters - likely gibberish
    
    # Check for common signs of extraction failure
    # Too many repeated characters
    if re.search(r'(.)\1{10,}', text):
        return False
    
    # Check if text has reasonable word-like patterns
    words = re.findall(r'\b\w+\b', text)
    if len(words) < 10:
        return False  # Too few words
    
    # Check average word length (should be reasonable)
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 0
    if avg_word_len < 2 or avg_word_len > 20:
        return False  # Unusual word lengths
    
    return True


def compare_text_quality(pymupdf_text: str, mistral_text: str, was_quality_poor: bool = False) -> Tuple[str, Dict]:
    """
    Compare extraction quality between PyMuPDF and Mistral OCR using multiple metrics
    
    Args:
        pymupdf_text: Text extracted by PyMuPDF
        mistral_text: Text extracted by Mistral OCR
        was_quality_poor: Whether PyMuPDF quality was flagged as poor
        
    Returns:
        Tuple of (winning_method_name, comparison_details_dict)
    """
    def calculate_metrics(text: str) -> Dict:
        """Calculate quality metrics for text"""
        if not text or len(text.strip()) == 0:
            return {
                "char_count": 0,
                "word_count": 0,
                "alphanumeric_ratio": 0.0,
                "avg_word_length": 0.0,
                "readable_words": 0,
                "readable_ratio": 0.0
            }
        
        # Basic counts
        char_count = len(text)
        words = re.findall(r'\b\w+\b', text)
        word_count = len(words)
        
        # Alphanumeric ratio
        alphanumeric = sum(c.isalnum() or c.isspace() for c in text)
        alphanumeric_ratio = alphanumeric / char_count if char_count > 0 else 0
        
        # Average word length
        avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
        
        # Readable words (reasonable length, mostly letters)
        readable_words = sum(1 for w in words if 2 <= len(w) <= 20 and sum(c.isalpha() for c in w) / len(w) > 0.7)
        readable_ratio = readable_words / word_count if word_count > 0 else 0
        
        return {
            "char_count": char_count,
            "word_count": word_count,
            "alphanumeric_ratio": alphanumeric_ratio,
            "avg_word_length": avg_word_length,
            "readable_words": readable_words,
            "readable_ratio": readable_ratio
        }
    
    # Calculate metrics for both
    pymupdf_metrics = calculate_metrics(pymupdf_text)
    mistral_metrics = calculate_metrics(mistral_text)
    
    # Decision logic
    winner = "PyMuPDF"
    reason = ""
    
    # If Mistral extraction is obviously broken (too few characters)
    if mistral_metrics["char_count"] < 100:
        winner = "PyMuPDF"
        reason = "Mistral OCR extraction appears incomplete or failed"
    
    # If PyMuPDF extraction is obviously broken
    elif pymupdf_metrics["char_count"] < 100:
        winner = "Mistral OCR"
        reason = "PyMuPDF extraction appears incomplete or failed"
    
    # If quality was already flagged as poor, strongly prefer Mistral unless it's clearly worse
    elif was_quality_poor:
        # Compare quality metrics
        mistral_score = (
            mistral_metrics["alphanumeric_ratio"] * 0.4 +
            mistral_metrics["readable_ratio"] * 0.4 +
            (1.0 if 3 <= mistral_metrics["avg_word_length"] <= 8 else 0.5) * 0.2
        )
        
        pymupdf_score = (
            pymupdf_metrics["alphanumeric_ratio"] * 0.4 +
            pymupdf_metrics["readable_ratio"] * 0.4 +
            (1.0 if 3 <= pymupdf_metrics["avg_word_length"] <= 8 else 0.5) * 0.2
        )
        
        # Prefer Mistral if it's reasonably good (score > 0.6) or better than PyMuPDF
        if mistral_score > 0.6 or mistral_score > pymupdf_score:
            winner = "Mistral OCR"
            reason = "Better quality metrics (poor quality was flagged)"
        else:
            winner = "PyMuPDF"
            reason = "Mistral OCR quality also poor, using PyMuPDF"
    
    # Both seem good quality - use more nuanced comparison
    else:
        # Calculate composite quality scores
        mistral_score = (
            mistral_metrics["alphanumeric_ratio"] * 0.3 +
            mistral_metrics["readable_ratio"] * 0.3 +
            (mistral_metrics["word_count"] / max(mistral_metrics["char_count"], 1) * 10) * 0.2 +  # Word density
            (1.0 if 3 <= mistral_metrics["avg_word_length"] <= 8 else 0.5) * 0.2
        )
        
        pymupdf_score = (
            pymupdf_metrics["alphanumeric_ratio"] * 0.3 +
            pymupdf_metrics["readable_ratio"] * 0.3 +
            (pymupdf_metrics["word_count"] / max(pymupdf_metrics["char_count"], 1) * 10) * 0.2 +
            (1.0 if 3 <= pymupdf_metrics["avg_word_length"] <= 8 else 0.5) * 0.2
        )
        
        # Prefer Mistral if clearly better quality
        if mistral_score > pymupdf_score * 1.1:  # 10% better threshold
            winner = "Mistral OCR"
            reason = "Better quality metrics"
        elif pymupdf_score > mistral_score * 1.1:
            winner = "PyMuPDF"
            reason = "Better quality metrics"
        else:
            # Similar quality - prefer PyMuPDF (free)
            winner = "PyMuPDF"
            reason = "Similar quality, using free extraction"
    
    # Prepare detailed comparison for logging
    comparison = {
        "pymupdf": pymupdf_metrics,
        "mistral": mistral_metrics,
        "winner": winner,
        "reason": reason
    }
    
    return winner, comparison


def render_page_to_image(page, dpi: int = 300) -> bytes:
    """
    Render a PDF page to an image for OCR
    
    Args:
        page: PyMuPDF page object
        dpi: Resolution for rendering (default 300 for OCR quality, 300+ recommended for GPT-4V)
        
    Returns:
        Image bytes (PNG format)
    """
    # Render page to pixmap at specified DPI
    mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 is default PDF DPI
    pix = page.get_pixmap(matrix=mat)
    
    # Convert to PNG bytes
    img_bytes = pix.tobytes("png")
    
    return img_bytes


class DocumentReader:
    """Base class for document readers"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.document_name = self.file_path.stem
        
    def read_text(self) -> Dict[str, any]:
        """Read text content from document"""
        raise NotImplementedError
        
    def read_images(self) -> List[Tuple[int, str, str]]:
        """Extract embedded images from document
        
        Returns:
            List of (page_number, image_base64, context_text) tuples
        """
        raise NotImplementedError


class PDFReader(DocumentReader):
    """PDF document reader using PyMuPDF (fitz)"""
    
    def __init__(self, file_path: str):
        super().__init__(file_path)
        if not PDF_AVAILABLE:
            raise ImportError("PyMuPDF not installed. Run: pip install PyMuPDF")
    
    def read_text(self) -> Dict[str, any]:
        """Extract text from PDF using PyMuPDF"""
        result = {
            "text": "",
            "pages": [],
            "number_of_pages": 0,
            "metadata": {},
            "has_images": False
        }
        
        try:
            doc = fitz.open(str(self.file_path))
            result["number_of_pages"] = len(doc)
            
            # Extract text page by page
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_text = page.get_text()
                
                result["pages"].append({
                    "page_number": page_num + 1,
                    "text": page_text
                })
                result["text"] += f"\n--- Page {page_num + 1} ---\n{page_text}"
                
                # Check if page has images
                image_list = page.get_images(full=True)
                if image_list:
                    result["has_images"] = True
            
            # Extract metadata
            metadata = doc.metadata
            if metadata:
                result["metadata"] = {
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "subject": metadata.get("subject", ""),
                    "creator": metadata.get("creator", ""),
                }
            
            doc.close()
            
        except Exception as e:
            raise Exception(f"Error reading PDF: {e}")
            
        return result
    
    def read_images(self) -> List[Tuple[int, str, str]]:
        """Extract embedded images from PDF
        
        Returns:
            List of (page_number, image_base64, context_text) tuples
        """
        if not PIL_AVAILABLE:
            print("Warning: Pillow not installed. Image extraction may be limited.")
        
        images = []
        
        try:
            doc = fitz.open(str(self.file_path))
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                
                # Get text from this page for context
                page_text = page.get_text()
                
                for img_index, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Filter out tiny images (likely logos, bullets, etc.)
                        if base_image["width"] < 100 or base_image["height"] < 100:
                            continue
                        
                        # Convert to base64
                        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
                        
                        # Extract context text around the image
                        # Get a snippet of text from the same page
                        context = self._extract_image_context(page_text, page_num + 1)
                        
                        images.append((page_num + 1, img_base64, context))
                        
                    except Exception as e:
                        print(f"Warning: Could not extract image {img_index} from page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
        except Exception as e:
            print(f"Warning: Could not extract images from PDF: {e}")
            
        return images
    
    def _extract_image_context(self, page_text: str, page_num: int) -> str:
        """Extract context text around an image
        
        Args:
            page_text: Full text of the page
            page_num: Page number
            
        Returns:
            Context string describing where the image appears
        """
        # Look for figure/diagram references
        lines = page_text.split('\n')
        context_lines = []
        
        for line in lines[:10]:  # First 10 lines often contain question/context
            line = line.strip()
            if line and len(line) > 10:
                context_lines.append(line)
                if len(context_lines) >= 3:
                    break
        
        context = " ".join(context_lines)
        if context:
            return f"Page {page_num}: {context[:200]}..."
        else:
            return f"Page {page_num}"
    
    def render_pages_for_ocr(self, dpi: int = 300) -> List[Tuple[int, bytes]]:
        """
        Render all PDF pages as images for OCR processing
        
        Args:
            dpi: Resolution for rendering (default 300 for good OCR quality, 300+ recommended for GPT-4V)
            
        Returns:
            List of (page_number, image_bytes) tuples
        """
        page_images = []
        
        try:
            doc = fitz.open(str(self.file_path))
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # Render page to image
                img_bytes = render_page_to_image(page, dpi)
                page_images.append((page_num + 1, img_bytes))  # 1-indexed
            
            doc.close()
            
        except Exception as e:
            print(f"Error rendering PDF pages: {e}")
        
        return page_images


class DOCXReader(DocumentReader):
    """DOCX document reader"""
    
    def read_text(self) -> Dict[str, any]:
        """Extract text from DOCX"""
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx not installed. Run: pip install python-docx")
        
        result = {
            "text": "",
            "pages": [],
            "number_of_pages": 1,  # DOCX doesn't have clear page boundaries
            "metadata": {},
            "has_images": False
        }
        
        doc = Document(self.file_path)
        
        # Extract all paragraphs
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text)
        
        text = "\n".join(paragraphs)
        result["text"] = text
        result["pages"].append({
            "page_number": 1,
            "text": text
        })
        
        # Check for inline images
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                result["has_images"] = True
                break
        
        # Try to get core properties
        try:
            core_props = doc.core_properties
            result["metadata"] = {
                "title": core_props.title or "",
                "author": core_props.author or "",
                "subject": core_props.subject or "",
            }
        except:
            pass
            
        return result
    
    def read_images(self) -> List[Tuple[int, str, str]]:
        """Extract images from DOCX"""
        # Could be implemented to extract embedded images from DOCX
        # For now, returning empty list as DOCX images are less common
        return []


class TXTReader(DocumentReader):
    """TXT document reader"""
    
    def read_text(self) -> Dict[str, any]:
        """Extract text from TXT file"""
        result = {
            "text": "",
            "pages": [],
            "number_of_pages": 1,
            "metadata": {},
            "has_images": False
        }
        
        with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        result["text"] = text
        result["pages"].append({
            "page_number": 1,
            "text": text
        })
        
        return result
    
    def read_images(self) -> List[Tuple[int, str, str]]:
        """TXT files don't have images"""
        return []


def get_reader(file_path: str) -> DocumentReader:
    """Factory function to get appropriate reader"""
    path = Path(file_path)
    suffix = path.suffix.lower()
    
    if suffix == ".pdf":
        return PDFReader(file_path)
    elif suffix == ".docx":
        return DOCXReader(file_path)
    elif suffix == ".txt":
        return TXTReader(file_path)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")
