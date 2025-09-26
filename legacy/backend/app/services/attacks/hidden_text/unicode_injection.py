"""
Unicode Injection Renderer

Implements hidden text injection using invisible Unicode characters.
This is the current method used in the existing codebase.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)

class UnicodeInjectionRenderer:
    """
    Renders hidden text using invisible Unicode characters.
    
    This method embeds invisible Unicode characters (ZWSP, ZWNJ, ZWJ, etc.)
    in the PDF text content. The characters are invisible to human readers
    but can be parsed by LLMs.
    """
    
    def __init__(self):
        # Import Unicode characters from attack_service
        from ..attack_service import ZWSP, ZWNJ, ZWJ, LRM, RLM
        self.unicode_chars = {
            'ZWSP': ZWSP,  # Zero-Width Space
            'ZWNJ': ZWNJ,  # Zero-Width Non-Joiner  
            'ZWJ': ZWJ,    # Zero-Width Joiner
            'LRM': LRM,    # Left-to-Right Mark
            'RLM': RLM     # Right-to-Left Mark
        }
        
        logger.info("[REFACTOR][UNICODE_INJECTION] Initialized Unicode injection renderer")
    
    def inject_hidden_text(
        self,
        page: fitz.Page,
        text: str,
        x: float,
        y: float,
        fontsize: float = 1.0
    ) -> None:
        """
        Inject hidden text using invisible Unicode characters.
        
        Args:
            page: PyMuPDF page object
            text: Text to inject (already wrapped with Unicode chars)
            x: X coordinate for injection
            y: Y coordinate for injection  
            fontsize: Font size (very small to minimize visual impact)
        """
        try:
            # Insert as tiny white text to minimize visual impact
            # The Unicode cloaking makes it invisible regardless
            page.insert_text(
                (x, y), 
                text, 
                fontsize=fontsize, 
                color=(1, 1, 1)  # White color
            )
            
            logger.debug(
                "[REFACTOR][UNICODE_INJECTION] Injected hidden text at (%.1f, %.1f) length=%d",
                x, y, len(text)
            )
            
        except Exception as e:
            logger.error(
                "[REFACTOR][UNICODE_INJECTION] Failed to inject hidden text: %s", 
                str(e)
            )
    
    def wrap_text_with_unicode(self, text: str) -> str:
        """
        Wrap text with invisible Unicode characters for cloaking.
        
        Args:
            text: Original text to wrap
            
        Returns:
            Text wrapped with invisible Unicode characters
        """
        zwsp = self.unicode_chars['ZWSP']
        zwnj = self.unicode_chars['ZWNJ'] 
        zwj = self.unicode_chars['ZWJ']
        
        # Use same pattern as existing HIDDEN_INSTRUCTION_TEXT_PRIORITY_ALPHA
        wrapped = f"{zwsp}{zwnj}{zwj}{text}{zwj}{zwnj}{zwsp}"
        
        logger.debug(
            "[REFACTOR][UNICODE_INJECTION] Wrapped text with Unicode chars: %d -> %d chars",
            len(text), len(wrapped)
        )
        
        return wrapped
    
    def inject_global_directive(
        self,
        page: fitz.Page,
        directive: str,
        page_width: float,
        page_height: float
    ) -> None:
        """
        Inject global directive at the top of the page.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            page_width: Page width for positioning
            page_height: Page height for positioning
        """
        # Position at top-left corner with small offset
        x = 10.0
        y = 20.0
        
        # Wrap directive with Unicode cloaking
        wrapped_directive = self.wrap_text_with_unicode(directive)
        
        self.inject_hidden_text(page, wrapped_directive, x, y, fontsize=0.1)
        
        logger.debug(
            "[REFACTOR][UNICODE_INJECTION] Injected global directive at page top"
        )
    
    def inject_per_question_directive(
        self,
        page: fitz.Page,
        directive: str,
        question_bbox: tuple,
        question_id: str
    ) -> None:
        """
        Inject directive before a specific question to ensure proper parsing order.
        
        Args:
            page: PyMuPDF page object
            directive: Directive text to inject
            question_bbox: (x0, y0, x1, y1) bounding box of question
            question_id: Question identifier for logging
        """
        x0, y0, x1, y1 = question_bbox
        
        # Position just before the question, aligned to its left edge
        x = max(x0 - 2.0, 1.0)
        y = max(y0 - 4.0, 1.0)
        
        # For detection mode, include the full wrong answer as part of directive
        # This ensures the LLM sees the wrong answer before processing the question
        wrapped_directive = self.wrap_text_with_unicode(directive)
        
        self.inject_hidden_text(page, wrapped_directive, x, y, fontsize=0.1)
        
        logger.debug(
            "[REFACTOR][UNICODE_INJECTION] Injected per-question directive for %s at (%.1f, %.1f) - placed just before question",
            question_id, x, y
        )