from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

from ....utils.logging import get_logger
from ..latex_icw_service import LatexICWService
from ..latex_dual_layer_service import LatexAttackService
from ..latex_font_attack_service import LatexFontAttackService
from .base_renderer import BaseRenderer

logger = get_logger(__name__)


class LatexICWRenderer(BaseRenderer):
    """Renderer that injects hidden prompts and returns the ICW-only PDF."""

    def __init__(self) -> None:
        super().__init__()
        self.icw_service = LatexICWService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002
    ) -> Dict[str, float | str | int | None]:
        result = self.icw_service.execute(run_id, force=False)
        artifacts = result.get("artifacts") or {}
        final_pdf_path = artifacts.get("final_pdf")

        destination.parent.mkdir(parents=True, exist_ok=True)
        if final_pdf_path:
            final_path = Path(final_pdf_path)
            if final_path.exists():
                shutil.copy2(final_path, destination)
            else:
                logger.error(
                    f"ICW PDF compilation failed: {final_pdf_path} does not exist. "
                    f"Check LaTeX compilation logs for run_id: {run_id}"
                )
                raise RuntimeError(f"ICW PDF compilation failed for latex_icw")
        else:
            logger.error(f"ICW service returned no PDF path for run_id: {run_id}")
            raise RuntimeError(f"ICW service execution failed for latex_icw")

        summary = result.get("compile_summary") or {}
        metadata = {
            "file_size_bytes": destination.stat().st_size if destination.exists() else 0,
            "prompt_count": len(result.get("instructions") or []),
            "style": result.get("style"),
            "compile_success": bool(summary.get("success")),
            "tex_source": result.get("tex_source"),
        }
        return metadata


class LatexICWDualLayerRenderer(BaseRenderer):
    """Renderer that chains ICW prompts with the dual layer visual attack."""

    def __init__(self) -> None:
        super().__init__()
        self.icw_service = LatexICWService()
        self.dual_service = LatexAttackService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002
    ) -> Dict[str, float | str | int | None]:
        icw_result = self.icw_service.execute(run_id, force=False)
        icw_artifacts = icw_result.get("artifacts") or {}
        icw_tex_path = icw_artifacts.get("attacked_tex")

        dual_result = self.dual_service.execute(
            run_id,
            method_name="latex_icw_dual_layer",
            force=False,
            tex_override=Path(icw_tex_path) if icw_tex_path else None,
        )

        artifacts = dual_result.get("artifacts") or {}
        final_pdf_path_str = artifacts.get("final_pdf") or artifacts.get("enhanced_pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Verify ICW stage succeeded
        if not icw_tex_path or not Path(icw_tex_path).exists():
            logger.error(
                f"ICW+DualLayer failed at ICW stage. "
                f"Intermediate TeX missing: {icw_tex_path} for run_id: {run_id}"
            )
            raise RuntimeError(f"ICW stage failed for latex_icw_dual_layer")

        if final_pdf_path_str:
            final_pdf_path = Path(final_pdf_path_str)
            if final_pdf_path.exists():
                shutil.copy2(final_pdf_path, destination)
            else:
                logger.error(
                    f"ICW+DualLayer failed at dual layer stage. "
                    f"Final PDF missing: {final_pdf_path_str} for run_id: {run_id}"
                )
                raise RuntimeError(f"Dual layer stage failed for latex_icw_dual_layer")
        else:
            logger.error(f"Dual layer service returned no PDF path for run_id: {run_id}")
            raise RuntimeError(f"Dual layer service execution failed for latex_icw_dual_layer")

        metadata = dual_result.get("renderer_metadata") or {}
        metadata.setdefault("prompt_count", len(icw_result.get("instructions") or []))
        metadata["file_size_bytes"] = destination.stat().st_size if destination.exists() else 0
        metadata.setdefault("compile_summary", dual_result.get("compile_summary"))
        metadata.setdefault("tex_source", dual_result.get("tex_source"))
        return metadata


class LatexICWFontAttackRenderer(BaseRenderer):
    """Renderer that chains ICW prompts with the font attack."""

    def __init__(self) -> None:
        super().__init__()
        self.icw_service = LatexICWService()
        self.font_service = LatexFontAttackService()

    def render(
        self,
        run_id: str,
        original_pdf: Path,  # noqa: ARG002
        destination: Path,
        mapping: Dict[str, str],  # noqa: ARG002
    ) -> Dict[str, float | str | int | None]:
        icw_result = self.icw_service.execute(run_id, force=False)
        icw_artifacts = icw_result.get("artifacts") or {}
        icw_tex_path = icw_artifacts.get("attacked_tex")

        font_result = self.font_service.execute(
            run_id,
            force=False,
            tex_override=Path(icw_tex_path) if icw_tex_path else None,
            artifact_label="latex-icw-font-attack",
            record_method="latex_icw_font_attack",
        )

        artifacts = font_result.get("artifacts") or {}
        final_pdf_path = artifacts.get("final_pdf")

        destination.parent.mkdir(parents=True, exist_ok=True)

        # Verify ICW stage succeeded
        if not icw_tex_path or not Path(icw_tex_path).exists():
            logger.error(
                f"ICW+FontAttack failed at ICW stage. "
                f"Intermediate TeX missing: {icw_tex_path} for run_id: {run_id}"
            )
            raise RuntimeError(f"ICW stage failed for latex_icw_font_attack")

        if final_pdf_path:
            final_pdf = Path(final_pdf_path)
            if final_pdf.exists():
                shutil.copy2(final_pdf, destination)
            else:
                logger.error(
                    f"ICW+FontAttack failed at font attack stage. "
                    f"Final PDF missing: {final_pdf_path} for run_id: {run_id}"
                )
                raise RuntimeError(f"Font attack stage failed for latex_icw_font_attack")
        else:
            logger.error(f"Font attack service returned no PDF path for run_id: {run_id}")
            raise RuntimeError(f"Font attack service execution failed for latex_icw_font_attack")

        compile_summary = font_result.get("compile_summary") or {}
        metadata = {
            "file_size_bytes": destination.stat().st_size if destination.exists() else 0,
            "prompt_count": len(icw_result.get("instructions") or []),
            "compile_success": bool(compile_summary.get("success")),
            "compile_summary": compile_summary,
            "fonts_generated": sum(
                len(entry.get("fonts") or []) for entry in font_result.get("attacks") or []
            ),
            "tex_source": font_result.get("tex_source"),
        }
        return metadata
