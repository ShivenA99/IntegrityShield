"""
ActualText Injection Renderer

Implements hidden text injection using PDF ActualText property.
This method embeds text in the PDF structure itself rather than visible content.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

class ActualTextInjectionRenderer:
    """
    Renders hidden text using PDF ActualText property.
    
    This method embeds text in the PDF's actual text property, which can be
    read by text extraction tools and LLMs but is not visually displayed.
    More sophisticated than simple text injection.
    """
    
    def __init__(self):
        logger.info("[REFACTOR][ACTUALTEXT] Initialized ActualText injection renderer")
    
    def inject_hidden_text(
        self,
        page: fitz.Page,
        text: str,
        x: float,
        y: float,
        fontsize: float = 1.0
    ) -> None:
        """
        Inject hidden text using ActualText property.
        
        Args:
            page: PyMuPDF page object
            text: Text to inject
            x: X coordinate for injection
            y: Y coordinate for injection
            fontsize: Font size (used for positioning calculation)
        """
        try:
            # Create a transparent rectangle with ActualText
            rect = fitz.Rect(x, y, x + 1, y + 1)  # Tiny 1x1 rectangle
            
            # Insert transparent text with ActualText property
            # This approach embeds the text in the PDF structure
            text_writer = fitz.TextWriter(page.rect)
            text_writer.append(
                (x, y),
                text,
                fontsize=0.1,  # Very small but not zero
                color=(1, 1, 1)  # White color
            )
            
            # Write to page
            text_writer.write_text(page)
            
            logger.debug(
                "[REFACTOR][ACTUALTEXT] Injected ActualText at (%.1f, %.1f) length=%d",
                x, y, len(text)
            )
            
        except Exception as e:
            logger.error(
                "[REFACTOR][ACTUALTEXT] Failed to inject ActualText: %s",
                str(e)
            )
            
            # Fallback to simple text insertion
            try:
                page.insert_text(
                    (x, y),
                    text,
                    fontsize=fontsize,
                    color=(1, 1, 1)
                )
                logger.debug("[REFACTOR][ACTUALTEXT] Used fallback text insertion")
            except Exception as e2:
                logger.error("[REFACTOR][ACTUALTEXT] Fallback also failed: %s", str(e2))
    
    def inject_global_directive(
        self,
        page: fitz.Page,
        directive: str,
        page_width: float,
        page_height: float
    ) -> None:
        """
        Inject global directive using ActualText at page top.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            page_width: Page width for positioning
            page_height: Page height for positioning
        """
        # Position at top-left corner
        x = 1.0
        y = 10.0
        
        self.inject_hidden_text(page, directive, x, y)
        
        logger.debug("[REFACTOR][ACTUALTEXT] Injected global directive using ActualText")
    
    def inject_per_question_directive(
        self,
        page: fitz.Page,
        directive: str,
        question_bbox: tuple,
        question_id: str
    ) -> None:
        """
        Inject directive near a specific question using ActualText.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            question_bbox: (x0, y0, x1, y1) bounding box of question
            question_id: Question identifier for logging
        """
        x0, y0, x1, y1 = question_bbox
        
        # Position near the question start
        x = max(x0 - 2.0, 1.0)  # Slightly to the left
        y = y0
        
        self.inject_hidden_text(page, directive, x, y)
        
        logger.debug(
            "[REFACTOR][ACTUALTEXT] Injected per-question directive for %s using ActualText",
            question_id
        )
    
    def inject_structured_text(
        self,
        page: fitz.Page,
        text_blocks: List[Dict[str, Any]],
        page_width: float,
        page_height: float
    ) -> None:
        """
        Inject multiple structured text blocks using ActualText.
        
        This method allows for more sophisticated text embedding
        with different positioning strategies.
        
        Args:
            page: PyMuPDF page object
            text_blocks: List of text blocks with position info
            page_width: Page width
            page_height: Page height
        """
        for i, block in enumerate(text_blocks):
            text = block.get("text", "")
            position = block.get("position", {})
            
            x = position.get("x", 10.0 + i * 20.0)
            y = position.get("y", 10.0 + i * 5.0)
            
            if text.strip():
                self.inject_hidden_text(page, text, x, y)
        
        logger.debug(
            "[REFACTOR][ACTUALTEXT] Injected %d structured text blocks",
            len(text_blocks)
        )
    
    def create_invisible_annotation(
        self,
        page: fitz.Page,
        text: str,
        rect: fitz.Rect
    ) -> None:
        """
        Create an invisible annotation with hidden text.
        
        This method creates a PDF annotation that contains the hidden text
        but is not visually displayed to users.
        
        Args:
            page: PyMuPDF page object
            text: Text to embed in annotation
            rect: Rectangle for annotation placement
        """
        try:
            # Create a text annotation with invisible content
            annot = page.add_text_annot(rect.tl, text)
            annot.set_info(content=text)
            annot.update()
            
            # Make annotation invisible
            annot.set_flags(fitz.PDF_ANNOT_HIDDEN | fitz.PDF_ANNOT_INVISIBLE)
            annot.update()
            
            logger.debug(
                "[REFACTOR][ACTUALTEXT] Created invisible annotation with text length=%d",
                len(text)
            )
            
        except Exception as e:
            logger.error(
                "[REFACTOR][ACTUALTEXT] Failed to create invisible annotation: %s",
                str(e)
            )