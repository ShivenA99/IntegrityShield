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


class DocumentEnhancementService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.latex_service = LatexAttackService()

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        methods = config.get("enhancement_methods") or [
            "latex_dual_layer",
            "pymupdf_overlay",
        ]
        return await asyncio.to_thread(self._prepare_methods, run_id, methods)

    def _prepare_methods(self, run_id: str, methods: Iterable[str]) -> Dict[str, Any]:
        structured = self.structured_manager.load(run_id) or {}
        enhanced_map: Dict[str, Dict] = {}

        EnhancedPDF.query.filter_by(pipeline_run_id=run_id).delete()
        db.session.commit()

        for method in methods:
            pdf_path = enhanced_pdf_path(run_id, method)
            enhanced = EnhancedPDF(
                pipeline_run_id=run_id,
                method_name=method,
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
        if "latex_dual_layer" in methods:
            try:
                summaries["latex_dual_layer"] = self.latex_service.execute(run_id, force=True)
                structured = self.structured_manager.load(run_id) or structured
            except Exception as exc:
                self.logger.warning(
                    "Latex dual-layer generation failed",
                    extra={"run_id": run_id, "error": str(exc)},
                )
                summaries["latex_dual_layer"] = {"error": str(exc)}
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
