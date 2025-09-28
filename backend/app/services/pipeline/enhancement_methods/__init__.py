from __future__ import annotations

from typing import Dict, Type

from .base_renderer import BaseRenderer
from .content_stream_renderer import ContentStreamRenderer
from .dual_layer_renderer import DualLayerRenderer
from .font_manipulation_renderer import FontManipulationRenderer
from .image_overlay_renderer import ImageOverlayRenderer
from .pymupdf_renderer import PyMuPDFRenderer

RENDERERS: Dict[str, Type[BaseRenderer]] = {
    "dual_layer": DualLayerRenderer,
    "image_overlay": ImageOverlayRenderer,
    "font_manipulation": FontManipulationRenderer,
    "content_stream_overlay": ContentStreamRenderer,
    "content_stream": ContentStreamRenderer,
    "pymupdf_overlay": PyMuPDFRenderer,
}

__all__ = ["RENDERERS", "BaseRenderer"]
