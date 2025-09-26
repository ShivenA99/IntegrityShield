"""
Tiny Text Injection Renderer

Implements hidden text injection using extremely small white text.
Alternative method for hidden text that doesn't rely on Unicode cloaking.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

class TinyTextInjectionRenderer:
    """
    Renders hidden text using tiny white text at very small font size.
    
    This method places text at 0.1pt font size in white color, making it
    essentially invisible to human readers but still parseable by OCR/LLMs.
    """
    
    def __init__(self):
        self.tiny_fontsize = 0.1  # Extremely small font size
        self.white_color = (1, 1, 1)  # White color (RGB)
        
        logger.info("[REFACTOR][TINY_TEXT] Initialized tiny text injection renderer")
    
    def inject_hidden_text(
        self,
        page: fitz.Page,
        text: str,
        x: float,
        y: float,
        fontsize: float = None
    ) -> None:
        """
        Inject hidden text using tiny white text.
        
        Args:
            page: PyMuPDF page object
            text: Text to inject
            x: X coordinate for injection
            y: Y coordinate for injection
            fontsize: Font size override (defaults to tiny_fontsize)
        """
        try:
            actual_fontsize = fontsize if fontsize is not None else self.tiny_fontsize
            
            # Insert as tiny white text
            page.insert_text(
                (x, y),
                text,
                fontsize=actual_fontsize,
                color=self.white_color
            )
            
            logger.debug(
                "[REFACTOR][TINY_TEXT] Injected tiny text at (%.1f, %.1f) size=%.2f length=%d",
                x, y, actual_fontsize, len(text)
            )
            
        except Exception as e:
            logger.error(
                "[REFACTOR][TINY_TEXT] Failed to inject tiny text: %s",
                str(e)
            )
    
    def inject_global_directive(
        self,
        page: fitz.Page,
        directive: str,
        page_width: float,
        page_height: float
    ) -> None:
        """
        Inject global directive at the top of the page using tiny text.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            page_width: Page width for positioning
            page_height: Page height for positioning
        """
        # Position at top-left corner with small offset
        x = 5.0
        y = 15.0
        
        self.inject_hidden_text(page, directive, x, y)
        
        logger.debug("[REFACTOR][TINY_TEXT] Injected global directive at page top")
    
    def inject_per_question_directive(
        self,
        page: fitz.Page,
        directive: str,
        question_bbox: tuple,
        question_id: str
    ) -> None:
        """
        Inject directive near a specific question using tiny text.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            question_bbox: (x0, y0, x1, y1) bounding box of question
            question_id: Question identifier for logging
        """
        x0, y0, x1, y1 = question_bbox
        
        # Position slightly above the question
        x = x0
        y = max(y0 - 3.0, 5.0)  # Ensure we don't go off-page
        
        self.inject_hidden_text(page, directive, x, y)
        
        logger.debug(
            "[REFACTOR][TINY_TEXT] Injected per-question directive for %s at (%.1f, %.1f)",
            question_id, x, y
        )
    
    def inject_distributed_text(
        self,
        page: fitz.Page,
        text: str,
        page_width: float,
        page_height: float,
        num_positions: int = 5
    ) -> None:
        """
        Inject text at multiple distributed positions across the page.
        
        This method spreads the hidden text across multiple locations
        to increase the chance of LLM parsing while remaining invisible.
        
        Args:
            page: PyMuPDF page object
            text: Text to inject
            page_width: Page width
            page_height: Page height
            num_positions: Number of positions to distribute text across
        """
        # Split text into chunks
        chunk_size = max(1, len(text) // num_positions)
        text_chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        
        # Calculate positions distributed across the page
        positions = []
        for i in range(num_positions):
            x = (page_width / (num_positions + 1)) * (i + 1)
            y = 10.0 + (i * 2.0)  # Stagger vertically slightly
            positions.append((x, y))
        
        # Inject text chunks at different positions
        for i, chunk in enumerate(text_chunks[:num_positions]):
            if chunk.strip():  # Only inject non-empty chunks
                x, y = positions[i]
                self.inject_hidden_text(page, chunk, x, y)
        
        logger.debug(
            "[REFACTOR][TINY_TEXT] Distributed text across %d positions",
            min(len(text_chunks), num_positions)
        )