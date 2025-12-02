from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable

from ...extensions import db
from ...models import EnhancedPDF
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...utils.logging import get_logger
from ...utils.storage_paths import enhanced_pdf_path
from ...utils.time import isoformat, utc_now
from .latex_dual_layer_service import LatexAttackService
from .latex_font_attack_service import LatexFontAttackService
from .latex_icw_service import LatexICWService
from .pdf_creation_service import get_method_display_name


class DocumentEnhancementService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.latex_service = LatexAttackService()
        self.font_attack_service = LatexFontAttackService()
        self.icw_service = LatexICWService()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        methods = config.get("enhancement_methods") or []
        mode = config.get("mode", "detection")
        return await asyncio.to_thread(self._prepare_methods, run_id, methods, mode)

    def _prepare_methods(self, run_id: str, methods: Iterable[str], mode: str = "detection") -> Dict[str, Any]:
        structured = self.structured_manager.load(run_id) or {}
        enhanced_map: Dict[str, Dict] = {}

        EnhancedPDF.query.filter_by(pipeline_run_id=run_id).delete()
        db.session.commit()

        methods_list = list(methods)
        for method in methods_list:
            pdf_path = enhanced_pdf_path(run_id, method)
            display_name = get_method_display_name(mode, method, methods_list)
            enhanced = EnhancedPDF(
                pipeline_run_id=run_id,
                method_name=method,
                display_name=display_name,
                file_path=str(pdf_path),
                generation_config={"method": method},
            )
            db.session.add(enhanced)
            enhanced_map[method] = {
                "path": str(pdf_path),
                "method": method,
                "effectiveness_score": None,
            }

        db.session.commit()

        manipulation_results = structured.setdefault("manipulation_results", {})
        existing_map = manipulation_results.setdefault("enhanced_pdfs", {})
        existing_map.update(enhanced_map)

        summaries: Dict[str, Any] = {}
        latex_variants: list[str] = []
        for method in methods:
            if isinstance(method, str) and method.startswith("latex_"):
                latex_variants.append(method)
        for method in dict.fromkeys(latex_variants):
            try:
                if method == "latex_font_attack":
                    summaries[method] = self.font_attack_service.execute(run_id, force=True)
                elif method == "latex_icw":
                    summaries[method] = self.icw_service.execute(run_id, force=True)
                elif method in ("latex_dual_layer", "latex_icw_dual_layer"):
                    summaries[method] = self.latex_service.execute(run_id, method_name=method, force=True)
                else:
                    # ICW combinations (latex_icw_font_attack) are handled by renderers, not here
                    self.logger.warning(
                        "Method should be handled by renderers",
                        extra={"run_id": run_id, "method": method},
                    )
                structured = self.structured_manager.load(run_id) or structured
            except Exception as exc:
                self.logger.warning(
                    "Latex overlay generation failed",
                    extra={"run_id": run_id, "method": method, "error": str(exc)},
                )
                summaries[method] = {"error": str(exc), "method": method}
                structured = self.structured_manager.load(run_id) or structured

        metadata = structured.setdefault("pipeline_metadata", {})
        stages_completed = set(metadata.get("stages_completed", []))
        stages_completed.add("document_enhancement")
        metadata.update(
            {
                "current_stage": "document_enhancement",
                "stages_completed": list(stages_completed),
                "last_updated": isoformat(utc_now()),
            }
        )
        self.structured_manager.save(run_id, structured)

        result: Dict[str, Any] = {"methods_prepared": list(methods)}
        if summaries:
            result["method_summaries"] = summaries
        return result
