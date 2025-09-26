"""
Hidden Text Attack Implementations

This package contains different methods for injecting hidden text into PDFs:
- Invisible Unicode characters 
- Tiny text rendering
- PDF ActualText property manipulation
"""

from .unicode_injection import UnicodeInjectionRenderer
from .tiny_text_injection import TinyTextInjectionRenderer
from .actualtext_injection import ActualTextInjectionRenderer

__all__ = [
    "UnicodeInjectionRenderer",
    "TinyTextInjectionRenderer", 
    "ActualTextInjectionRenderer"
]