from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

from ..latex_dual_layer_service import LatexAttackService
from .base_renderer import BaseRenderer


class LatexDualLayerRenderer(BaseRenderer):
    """Renderer wrapper around LatexAttackService for dual-layer LaTeX attacks."""

    def __init__(self) -> None:
        super().__init__()
        self.attack_service = LatexAttackService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002
    ) -> Dict[str, float | str | int | None]:
        result = self.attack_service.execute(run_id, force=False)
        artifacts = result.get("artifacts") or {}
        final_pdf_path_str = artifacts.get("final_pdf") or artifacts.get("enhanced_pdf")

        destination.parent.mkdir(parents=True, exist_ok=True)
        if final_pdf_path_str:
            final_pdf_path = Path(final_pdf_path_str)
            if final_pdf_path.exists():
                shutil.copy2(final_pdf_path, destination)
            else:
                destination.write_bytes(b"")
        else:
            destination.write_bytes(b"")

        metadata = dict(result.get("renderer_metadata") or {})
        metadata.setdefault("artifacts", artifacts)
        metadata.setdefault("compile_summary", result.get("compile_summary"))
        metadata.setdefault("overlay_summary", result.get("overlay_summary"))
        metadata.setdefault("effectiveness_score", None)
        metadata.setdefault("method", result.get("method", "latex_dual_layer"))
        metadata["file_size_bytes"] = (
            destination.stat().st_size if destination.exists() else 0
        )
        return metadata
