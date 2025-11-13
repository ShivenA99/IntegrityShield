"""
Utilities for building LaTeX font-based attacks.

The attack operates by assigning portions of the visual text to each character
of the hidden text, then cloning a baseline TrueType font so that the glyph
for every hidden character renders the desired visual fragment. Each position
receives its own derivative font which LaTeX activates locally during PDF
generation.
"""

from .chunking import AttackPlan, AttackPosition, ChunkPlanner
from .font_builder import FontAttackBuilder, FontBuildResult, FontBuildError, FontCache

__all__ = [
    "AttackPlan",
    "AttackPosition",
    "ChunkPlanner",
    "FontAttackBuilder",
    "FontBuildResult",
    "FontBuildError",
    "FontCache",
]
