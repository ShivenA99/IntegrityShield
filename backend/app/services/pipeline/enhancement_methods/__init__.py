from __future__ import annotations

from typing import Dict, Type

from .base_renderer import BaseRenderer
from .content_stream_renderer import ContentStreamRenderer
from .dual_layer_renderer import DualLayerRenderer
from .font_manipulation_renderer import FontManipulationRenderer
from .image_overlay_renderer import ImageOverlayRenderer
from .pymupdf_renderer import PyMuPDFRenderer
from .latex_dual_layer_renderer import LatexDualLayerRenderer
from .latex_font_attack_renderer import LatexFontAttackRenderer
from .latex_icw_renderer import (
    LatexICWRenderer,
    LatexICWDualLayerRenderer,
    LatexICWFontAttackRenderer,
)

RENDERERS: Dict[str, Type[BaseRenderer]] = {
    "dual_layer": DualLayerRenderer,
    "image_overlay": ImageOverlayRenderer,
    "font_manipulation": FontManipulationRenderer,
    "content_stream_overlay": ContentStreamRenderer,
    "content_stream": ContentStreamRenderer,
    "content_stream_span_overlay": ContentStreamRenderer,
    "pymupdf_overlay": PyMuPDFRenderer,
    "latex_dual_layer": LatexDualLayerRenderer,
    "latex_font_attack": LatexFontAttackRenderer,
    "latex_icw": LatexICWRenderer,
    "latex_icw_dual_layer": LatexICWDualLayerRenderer,
    "latex_icw_font_attack": LatexICWFontAttackRenderer,
}

__all__ = ["RENDERERS", "BaseRenderer"]
