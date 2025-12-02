"""
Prevention Font Library Loader

Provides instant access to pre-generated fonts for prevention mode.
All fonts use a single hidden character ('a') mapped to different visual characters.
"""
import json
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class PreventionFont:
    """Metadata for a pre-generated prevention font"""
    visual_char: str
    filename: str
    path: Path
    hidden_char: str


class PreventionFontLibrary:
    """
    Fast lookup service for pre-generated prevention fonts

    Usage:
        library = PreventionFontLibrary()
        font_path = library.get_font_for_char('A')  # Returns pre-generated font
    """

    DEFAULT_HIDDEN_CHAR = 'a'  # Universal hidden character

    def __init__(self, library_dir: Optional[Path] = None):
        """
        Initialize font library

        Args:
            library_dir: Path to font library directory (defaults to data/font_library/prevention)
        """
        if library_dir is None:
            # Default to data/font_library/prevention relative to backend root
            # From: app/services/pipeline/font_attack/prevention_font_library.py
            # Go up 5 levels: font_attack -> pipeline -> services -> app -> backend
            backend_root = Path(__file__).parent.parent.parent.parent.parent
            library_dir = backend_root / "data" / "font_library" / "prevention"

        self.library_dir = Path(library_dir)
        self.metadata_path = self.library_dir / "metadata.json"

        # Font lookup cache: {visual_char: PreventionFont}
        self._font_cache: Dict[str, PreventionFont] = {}

        # Load library if it exists
        self._loaded = False
        if self.library_dir.exists() and self.metadata_path.exists():
            self._load_library()

    def _load_library(self) -> None:
        """Load font library metadata"""
        try:
            with open(self.metadata_path, 'r') as f:
                metadata = json.load(f)

            # Build font cache
            for visual_char, font_data in metadata.get('fonts', {}).items():
                self._font_cache[visual_char] = PreventionFont(
                    visual_char=visual_char,
                    filename=font_data['filename'],
                    path=self.library_dir / font_data['filename'],
                    hidden_char=font_data.get('hidden_char', self.DEFAULT_HIDDEN_CHAR)
                )

            self._loaded = True

        except Exception as e:
            print(f"Warning: Failed to load prevention font library: {e}")
            self._loaded = False

    def is_loaded(self) -> bool:
        """Check if library is loaded and ready"""
        return self._loaded and len(self._font_cache) > 0

    def get_font_for_char(self, visual_char: str) -> Optional[Path]:
        """
        Get pre-generated font path for a visual character

        Args:
            visual_char: The character to display visually

        Returns:
            Path to pre-generated font, or None if not found
        """
        if not self.is_loaded():
            return None

        font = self._font_cache.get(visual_char)
        if font and font.path.exists():
            return font.path

        return None

    def get_hidden_char(self) -> str:
        """Get the universal hidden character used by this library"""
        return self.DEFAULT_HIDDEN_CHAR

    def get_available_chars(self) -> set:
        """Get set of all visual characters supported by this library"""
        return set(self._font_cache.keys())

    def get_library_stats(self) -> Dict:
        """Get library statistics"""
        return {
            'loaded': self.is_loaded(),
            'library_dir': str(self.library_dir),
            'total_fonts': len(self._font_cache),
            'hidden_char': self.get_hidden_char(),
            'available_chars': len(self.get_available_chars())
        }

    def verify_library(self) -> Dict[str, int]:
        """
        Verify library integrity

        Returns:
            Dict with counts: {'total': N, 'valid': N, 'missing': N}
        """
        total = len(self._font_cache)
        valid = 0
        missing = 0

        for font in self._font_cache.values():
            if font.path.exists():
                valid += 1
            else:
                missing += 1
                print(f"  Missing font: {font.filename}")

        return {
            'total': total,
            'valid': valid,
            'missing': missing
        }


# Global singleton instance
_global_library: Optional[PreventionFontLibrary] = None


def get_prevention_font_library() -> PreventionFontLibrary:
    """
    Get global prevention font library instance (singleton)

    Returns:
        PreventionFontLibrary instance
    """
    global _global_library
    if _global_library is None:
        _global_library = PreventionFontLibrary()
    return _global_library
