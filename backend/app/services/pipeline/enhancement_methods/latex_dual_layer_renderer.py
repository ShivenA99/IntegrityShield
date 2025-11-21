from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

from ..latex_dual_layer_service import LatexAttackService
from .base_renderer import BaseRenderer


class LatexDualLayerRenderer(BaseRenderer):
    """Renderer that triggers the LaTeX dual-layer pipeline and copies the final artifact."""

    def __init__(self) -> None:
        super().__init__()
        self.attack_service = LatexAttackService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002 - kept for signature compatibility
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002 - attack service pulls mappings directly
    ) -> Dict[str, float | str | int | None]:
        # This renderer only handles latex_dual_layer
        method_name = "latex_dual_layer"

        self.logger.info(
            "Starting latex-based render",
            extra={"run_id": run_id, "method": method_name},
        )

        result = self.attack_service.execute(run_id, method_name=method_name, force=False)
        artifacts = result.get("artifacts") or {}
        final_pdf_path_str = artifacts.get("final_pdf") or artifacts.get("enhanced_pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)

        if final_pdf_path_str:
            final_pdf_path = Path(final_pdf_path_str)
            try:
                if final_pdf_path.exists():
                    if final_pdf_path.resolve() != destination.resolve():
                        shutil.copy2(final_pdf_path, destination)
                else:
                    destination.write_bytes(b"")
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "Failed to copy latex-dual-layer artifact",
                    extra={"run_id": run_id, "error": str(exc)},
                )
                destination.write_bytes(b"")
        else:
            destination.write_bytes(b"")

        metadata = result.get("renderer_metadata") or {}
        if destination.exists():
            metadata["file_size_bytes"] = destination.stat().st_size
        else:
            metadata["file_size_bytes"] = 0

        metadata.setdefault("effectiveness_score", None)
        metadata.setdefault("replacements", metadata.get("replacement_summary", {}).get("total", 0))
        metadata.setdefault("overlay_applied", metadata.get("overlay_summary", {}).get("overlays", 0))
        metadata.setdefault(
            "overlay_targets",
            metadata.get("replacement_summary", {}).get("replaced", 0),
        )

        return metadata
