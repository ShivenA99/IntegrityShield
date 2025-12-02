"""
Docling Image Extractor - Modular Component

Handles image extraction from PDFs using Docling for better complex layout handling.
This is a separate, reusable module that can be integrated into any pipeline.
"""

import os
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path


class DoclingImageExtractor:
    """
    Modular image extractor using Docling for complex PDF layouts
    
    Features:
    - Better handling of complex layouts than PyMuPDF
    - Vector graphics and scientific diagrams
    - Multi-part figures and charts
    - Automatic background removal
    - Positioning metadata extraction
    """
    
    def __init__(self):
        """
        Initialize the Docling image extractor (lazy initialization).
        
        Docling import is deferred until actually needed to avoid slow startup time.
        """
        self.docling_available = None  # Lazy - will check when needed
        self._converter = None  # Cache DocumentConverter instance to avoid reinitialization
    
    def _check_docling_availability(self) -> bool:
        """
        Check if Docling is available and properly installed.
        
        This is called lazily when actually needed, not during __init__.
        """
        try:
            from docling.document_converter import DocumentConverter
            return True
        except ImportError:
            print("[WARN] Docling not installed. Please install with: pip install docling")
            return False
    
    def extract_images(self, pdf_path: str, assets_dir: str) -> List[Dict[str, Any]]:
        """
        Extract images from PDF using Docling for better complex layout handling.
        
        Docling is initialized lazily on first use to avoid slow startup time.
        
        Args:
            pdf_path: Path to input PDF
            assets_dir: Directory to save extracted images
            
        Returns:
            List of extracted image metadata
        """
        if not self.is_available():
            print("[ERROR] Docling not available - cannot extract images")
            return []
        
        # Get cached converter (creates it if needed)
        converter = self._get_converter()
        if converter is None:
            print("[ERROR] Failed to initialize Docling converter")
            return []
        
        os.makedirs(assets_dir, exist_ok=True)
        extracted = []
        
        try:
            # Convert PDF with Docling (using cached converter)
            print(f"[INFO] Processing PDF with Docling (configured for image extraction)...")
            result = converter.convert(pdf_path)
            
            # Extract images from Docling result
            # Docling stores images in different ways - let's check multiple possibilities
            images_to_process = []
            
            # Method 1: Check if document has 'pictures' attribute
            if hasattr(result, 'document') and hasattr(result.document, 'pictures'):
                images_to_process = result.document.pictures
                print(f"[DEBUG] Found {len(images_to_process)} pictures via document.pictures")
            
            # Method 2: Check if document has 'images' attribute
            elif hasattr(result, 'document') and hasattr(result.document, 'images'):
                images_to_process = result.document.images
                print(f"[DEBUG] Found {len(images_to_process)} images via document.images")
            
            # Method 3: Check if result has 'images' directly
            elif hasattr(result, 'images'):
                images_to_process = result.images
                print(f"[DEBUG] Found {len(images_to_process)} images via result.images")
            
            # Method 4: Check pages for images
            elif hasattr(result, 'document') and hasattr(result.document, 'pages'):
                print(f"[DEBUG] Checking {len(result.document.pages)} pages for images...")
                for page in result.document.pages:
                    if hasattr(page, 'pictures'):
                        images_to_process.extend(page.pictures)
                    elif hasattr(page, 'images'):
                        images_to_process.extend(page.images)
                print(f"[DEBUG] Found {len(images_to_process)} images via pages")
            
            if images_to_process:
                print(f"[DEBUG] Processing {len(images_to_process)} images...")
                for img_index, image in enumerate(images_to_process):
                    try:
                        print(f"[DEBUG] Image {img_index}: {type(image)}")
                        print(f"[DEBUG] Image attributes: {[attr for attr in dir(image) if not attr.startswith('_')]}")
                        
                        # Get image data - try different methods
                        image_bytes = None
                        
                        # Method 1: Try the 'image' attribute (ImageRef object)
                        if hasattr(image, 'image') and image.image is not None:
                            # Check if it's an ImageRef object with pil_image attribute
                            if hasattr(image.image, 'pil_image') and image.image.pil_image is not None:
                                try:
                                    import io
                                    img_buffer = io.BytesIO()
                                    image.image.pil_image.save(img_buffer, format='PNG')
                                    image_bytes = img_buffer.getvalue()
                                    print(f"[DEBUG] Using 'image.pil_image' method: {len(image_bytes)} bytes")
                                except Exception as e:
                                    print(f"[DEBUG] image.pil_image failed: {e}")
                            else:
                                print(f"[DEBUG] image.pil_image is None or not available")
                                image_bytes = None
                        
                        # Method 2: Try get_image() method with document
                        elif hasattr(image, 'get_image'):
                            try:
                                # get_image requires the document as parameter
                                pil_image = image.get_image(result.document)
                                if pil_image:
                                    # Convert PIL Image to bytes
                                    import io
                                    img_buffer = io.BytesIO()
                                    pil_image.save(img_buffer, format='PNG')
                                    image_bytes = img_buffer.getvalue()
                                    print(f"[DEBUG] Using 'get_image(doc)' method: {len(image_bytes)} bytes")
                                else:
                                    print(f"[DEBUG] get_image(doc) returned None")
                            except Exception as e:
                                print(f"[DEBUG] get_image(doc) failed: {e}")
                        
                        # Method 3: Try 'content' attribute
                        elif hasattr(image, 'content') and image.content is not None:
                            image_bytes = image.content
                            print(f"[DEBUG] Using 'content' attribute: {len(image_bytes)} bytes")
                        
                        # Method 4: Try 'data' attribute
                        elif hasattr(image, 'data') and image.data is not None:
                            image_bytes = image.data
                            print(f"[DEBUG] Using 'data' attribute: {len(image_bytes)} bytes")
                        
                        if image_bytes is None:
                            print(f"[DEBUG] No image data found in image {img_index} - skipping")
                            continue
                        
                        # Determine file extension
                        image_ext = "png"  # Default to PNG
                        if hasattr(image, 'format'):
                            image_ext = image.format.lower()
                        
                        # Get positioning information
                        bbox = [0, 0, 0, 0]  # Default bbox
                        page_num = 1  # Default page
                        
                        if hasattr(image, 'bbox'):
                            bbox = list(image.bbox) if image.bbox else [0, 0, 0, 0]
                        if hasattr(image, 'page'):
                            page_num = image.page + 1 if image.page is not None else 1
                        
                        # Classify image position
                        y_pos = bbox[1] if len(bbox) > 1 and bbox[1] > 0 else 0
                        page_height = 800  # Default page height
                        
                        # If bbox is invalid (all zeros), classify as content by default
                        if bbox == [0, 0, 0, 0] or y_pos == 0:
                            position_type = "content"  # Assume content if no position info
                        elif y_pos < page_height * 0.2:
                            position_type = "header/logo"
                        elif y_pos > page_height * 0.8:
                            position_type = "footer"
                        else:
                            position_type = "content"
                        
                        # Save image
                        filename = f"page{page_num}_img{img_index + 1}.{image_ext}"
                        img_path = os.path.join(assets_dir, filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                        
                        # Remove black background (if possible)
                        try:
                            self._remove_black_background(img_path)
                        except:
                            pass  # Silently continue if processing fails
                        
                        extracted.append({
                            "filename": filename,
                            "path": img_path,
                            "page": page_num,
                            "bbox": bbox,
                            "position_type": position_type,
                            "width": bbox[2] - bbox[0] if len(bbox) > 3 else 0,
                            "height": bbox[3] - bbox[1] if len(bbox) > 3 else 0
                        })
                        
                        print(f"[OK] Extracted image: {filename}")
                        
                    except Exception as e:
                        print(f"[WARN] Failed to process image {img_index + 1}: {e}")
                        continue
            
            print(f"[OK] Docling extracted {len(extracted)} image(s)")
            return extracted
            
        except Exception as e:
            print(f"[ERROR] Docling image extraction failed: {e}")
            return []
    
    def _remove_black_background(self, image_path: str):
        """
        Smart background removal: Only remove large solid black regions
        Preserves text and detailed graphics
        """
        try:
            from PIL import Image, ImageFilter
            import numpy as np
            
            img = Image.open(image_path)
            original_mode = img.mode
            
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            data = np.array(img)
            height, width = data.shape[:2]
            
            # Much more conservative threshold - only pure black (RGB < 10)
            # This avoids removing anti-aliased edges of text
            black_threshold = 10
            
            # Identify very dark pixels
            dark_mask = (data[:, :, 0] < black_threshold) & \
                       (data[:, :, 1] < black_threshold) & \
                       (data[:, :, 2] < black_threshold)
            
            # Only remove if a significant portion is black (likely background)
            black_ratio = np.sum(dark_mask) / (height * width)
            
            if black_ratio > 0.3:  # More than 30% black = likely has black background
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
                black_mask = (data[:, :, 0] < 5) & (data[:, :, 1] < 5) & (data[:, :, 2] < 5)
                data[black_mask] = [255, 255, 255, 255]
                
                result = Image.fromarray(data)
                result.save(image_path)
            except:
                pass  # Silently continue
        except Exception as e:
            # Any other error, just skip
            print(f"    ⚠ Background removal failed for {os.path.basename(image_path)}: {e}")
            pass
    
    def is_available(self) -> bool:
        """
        Check if Docling is available for use (lazy check).
        
        Returns:
            True if Docling is available, False otherwise
        """
        if self.docling_available is None:
            self.docling_available = self._check_docling_availability()
        return self.docling_available
    
    def _get_converter(self):
        """
        Get or create DocumentConverter instance (cached for performance).
        
        The converter is created only once and reused to avoid expensive reinitialization.
        
        Returns:
            DocumentConverter instance if Docling is available, None otherwise
        """
        if self._converter is None and self.is_available():
            try:
                # Import Docling components only when needed
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                
                # Configure Docling with proper image extraction settings
                opts = PdfPipelineOptions()
                opts.images_scale = 4.0  # Higher = better image clarity (4.0 = ~288 DPI)
                opts.generate_page_images = True
                opts.generate_picture_images = True
                opts.do_ocr = True  # Enable OCR for better text positioning
                opts.do_table_structure = True  # Enable table structure detection
                
                # Initialize Docling converter with image extraction options
                self._converter = DocumentConverter(format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
                })
                print("[INFO] Docling DocumentConverter initialized (cached for reuse)")
            except Exception as e:
                print(f"[WARN] Failed to initialize Docling converter: {e}")
                self.docling_available = False
                return None
        
        return self._converter
    
    def get_extractor_info(self) -> Dict[str, Any]:
        """Get information about the extractor"""
        return {
            "name": "DoclingImageExtractor",
            "version": "1.0.0",
            "description": "Modular image extractor using Docling for complex PDF layouts",
            "available": self.is_available(),  # Use lazy check
            "features": [
                "Complex layout handling",
                "Vector graphics extraction", 
                "Scientific diagrams",
                "Multi-part figures",
                "Automatic background removal",
                "Positioning metadata",
                "Lazy initialization (fast startup)"
            ]
        }
