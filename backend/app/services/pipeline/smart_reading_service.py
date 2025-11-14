from __future__ import annotations

import asyncio
import sys
import shutil
import json
from pathlib import Path
from typing import Any, Dict, List

import fitz
from ...models import PipelineRun
from ...services.data_management.file_manager import FileManager
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.developer.live_logging_service import live_logging_service
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...utils.storage_paths import run_directory

# Add data_extraction to path
data_extraction_path = Path(__file__).parent.parent.parent.parent / "data_extraction"
if str(data_extraction_path) not in sys.path:
    sys.path.insert(0, str(data_extraction_path))

try:
    from src.pipeline import QuestionExtractionPipeline
except ImportError:
    # Fallback: try relative import
    import importlib.util
    pipeline_path = data_extraction_path / "src" / "pipeline.py"
    if pipeline_path.exists():
        spec = importlib.util.spec_from_file_location("pipeline", pipeline_path)
        pipeline_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pipeline_module)
        QuestionExtractionPipeline = pipeline_module.QuestionExtractionPipeline
    else:
        raise ImportError(f"Cannot import QuestionExtractionPipeline from {data_extraction_path}")


class SmartReadingService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.file_manager = FileManager()
        self.structured_manager = StructuredDataManager()
        # Initialize data extraction pipeline
        self.data_extraction_pipeline = QuestionExtractionPipeline(
            use_openai=True,
            use_mistral=True,
            enable_latex=True,  # Always enabled
            latex_include_images=True,
            latex_compile_pdf=True
        )

    async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._process_pdf, run_id)

    def _process_pdf(self, run_id: str) -> Dict[str, Any]:
        run = PipelineRun.query.get(run_id)
        if not run:
            raise ValueError("Pipeline run not found")

        pdf_path = Path(run.original_pdf_path)

        live_logging_service.emit(
            run_id,
            "smart_reading",
            "INFO",
            "Starting data extraction pipeline processing",
            context={"pdf_path": str(pdf_path)}
        )

        # Step 1: Process PDF through data_extraction pipeline
        extraction_result = self.data_extraction_pipeline.process_document(
            str(pdf_path),
            output_path=None  # Let pipeline determine output path
        )

        # Step 2: Copy output files (.tex, .pdf, .json) to pipeline_runs/run_id/
        copied_files = self._copy_extraction_outputs(run_id, pdf_path, extraction_result)

        # Step 3: Transform data_extraction JSON format to structured.json format
        structured = self._transform_data_extraction_output(
            run_id, pdf_path, extraction_result, copied_files
        )

        # Step 4: Save structured data
        self.structured_manager.save(run_id, structured)

        live_logging_service.emit(
            run_id,
            "smart_reading",
            "INFO",
            "Data extraction pipeline processing completed",
            context={
                "questions_found": len(extraction_result.get("questions", [])),
                "pages": extraction_result.get("number_of_pages", 0),
                "files_copied": len(copied_files),
            }
        )

        return {
            "pages": int(extraction_result.get("number_of_pages", 0)) if isinstance(extraction_result.get("number_of_pages"), str) else extraction_result.get("number_of_pages", 0),
            "questions_found": len(extraction_result.get("questions", [])),
            "files_copied": len(copied_files),
        }

    def _copy_extraction_outputs(
        self, run_id: str, pdf_path: Path, extraction_result: Dict[str, Any]
    ) -> Dict[str, str]:
        """Copy .tex, .pdf, and .json files from data_extraction output to pipeline_runs/run_id/."""
        run_dir = run_directory(run_id)
        copied_files = {}
        
        # Find the output directory from data_extraction pipeline
        # The pipeline outputs to Output/latex_reconstruction/ for LaTeX files
        data_extraction_base = Path(__file__).parent.parent.parent.parent / "data_extraction"
        latex_output_dir = data_extraction_base / "Output" / "latex_reconstruction"
        api_output_dir = data_extraction_base / "Output" / "output_api"
        
        pdf_stem = pdf_path.stem
        
        # Find and copy .tex file
        tex_file = latex_output_dir / f"{pdf_stem}.tex"
        if tex_file.exists():
            dest_tex = run_dir / f"{pdf_stem}.tex"
            shutil.copy2(tex_file, dest_tex)
            copied_files["tex"] = str(dest_tex)
            self.logger.info(f"Copied .tex file to {dest_tex}", run_id=run_id)

            # Copy associated asset directory (e.g., extracted images referenced in LaTeX)
            asset_dir = latex_output_dir / f"{pdf_stem}_assets"
            if asset_dir.exists() and asset_dir.is_dir():
                dest_asset_dir = run_dir / asset_dir.name
                try:
                    shutil.copytree(asset_dir, dest_asset_dir, dirs_exist_ok=True)
                    copied_files["assets"] = str(dest_asset_dir)
                    self.logger.info(
                        f"Copied LaTeX asset directory to {dest_asset_dir}",
                        run_id=run_id,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.logger.warning(
                        f"Failed to copy asset directory {asset_dir}: {exc}",
                        run_id=run_id,
                    )
        else:
            self.logger.warning(f".tex file not found at {tex_file}", run_id=run_id)
        
        # Find and copy .pdf file (compiled LaTeX PDF)
        pdf_file = latex_output_dir / f"{pdf_stem}.pdf"
        if pdf_file.exists():
            dest_pdf = run_dir / f"{pdf_stem}_reconstructed.pdf"
            shutil.copy2(pdf_file, dest_pdf)
            copied_files["pdf"] = str(dest_pdf)
            self.logger.info(f"Copied .pdf file to {dest_pdf}", run_id=run_id)
        else:
            self.logger.warning(f".pdf file not found at {pdf_file}", run_id=run_id)
        
        # Find and copy .json file
        # Try output_api first (main extraction result)
        json_file = api_output_dir / f"{pdf_stem}_extracted.json"
        if not json_file.exists():
            # Try latex_reconstruction directory for structured JSON
            json_file = latex_output_dir / f"{pdf_stem}_structured.json"
        if json_file.exists():
            dest_json = run_dir / f"{pdf_stem}_extracted.json"
            shutil.copy2(json_file, dest_json)
            copied_files["json"] = str(dest_json)
            self.logger.info(f"Copied .json file to {dest_json}", run_id=run_id)
        else:
            self.logger.warning(f".json file not found at {json_file}", run_id=run_id)
            # Save the extraction_result as JSON if file not found
            dest_json = run_dir / f"{pdf_stem}_extracted.json"
            with open(dest_json, 'w', encoding='utf-8') as f:
                json.dump(extraction_result, f, indent=2, ensure_ascii=False)
            copied_files["json"] = str(dest_json)
            self.logger.info(f"Saved extraction_result as JSON to {dest_json}", run_id=run_id)
        
        return copied_files

    def _transform_data_extraction_output(
        self,
        run_id: str,
        pdf_path: Path,
        extraction_result: Dict[str, Any],
        copied_files: Dict[str, str]
    ) -> Dict[str, Any]:
        """Transform data_extraction JSON format to structured.json format."""
        structured = self.structured_manager.load(run_id)
        
        # Update pipeline metadata
        structured.setdefault("pipeline_metadata", {})
        structured["pipeline_metadata"].update(
            {
                "current_stage": "smart_reading",
                "stages_completed": ["smart_reading"],
                "last_updated": isoformat(utc_now()),
                "ai_extraction_enabled": True,
                "ai_sources_used": ["data_extraction_pipeline"],
                "data_extraction_outputs": copied_files
            }
        )
        
        # Transform document metadata
        pages = int(extraction_result.get("number_of_pages", 0)) if isinstance(extraction_result.get("number_of_pages"), str) else extraction_result.get("number_of_pages", 0)
        structured["document"] = {
            "source_path": str(pdf_path),
            "filename": pdf_path.name,
            "pages": pages,
            "latex_path": copied_files.get("tex") if copied_files.get("tex") else None,
        }
        if copied_files.get("assets"):
            structured["document"]["assets_path"] = copied_files["assets"]
        structured["document"]["original_path"] = str(pdf_path)
        if copied_files.get("pdf"):
            structured["document"]["reconstructed_path"] = copied_files["pdf"]
            structured["document"]["pdf"] = copied_files["pdf"]
        
        # Transform questions to ai_questions format
        ai_questions = []
        for question in extraction_result.get("questions", []):
            # Map data_extraction format to existing format
            transformed_question = {
                "question_number": str(question.get("question_number", "")),
                "q_number": str(question.get("question_number", "")),
                "question_type": question.get("question_type", "mcq_single"),
                "stem_text": question.get("stem_text", ""),
                "options": question.get("options", {}),
                "gold_answer": question.get("gold_answer"),
                "gold_confidence": question.get("gold_confidence", 0.9),
                "confidence": question.get("confidence", 0.95),
                "positioning": question.get("positioning", {}),
                "stem_bbox": question.get("positioning", {}).get("stem_bbox") or question.get("positioning", {}).get("bbox"),
                "stem_spans": question.get("positioning", {}).get("stem_spans", []),
                "metadata": question.get("metadata", {}),
                "sources_detected": ["data_extraction_pipeline"]
            }
            ai_questions.append(transformed_question)
        
        structured["ai_questions"] = ai_questions
        
        # Add AI extraction metadata
        structured["ai_extraction"] = {
            "source": "data_extraction_pipeline",
            "confidence": 0.95 if ai_questions else 0.0,
            "questions_found": len(ai_questions),
            "processing_time_ms": 0,  # Could track this if needed
            "cost_cents": 0,  # Could track this if needed
            "error": None,
            "raw_response": extraction_result
        }
        
        # Add assets section (empty for now, could extract from data_extraction if needed)
        structured.setdefault("assets", {
            "images": [],
            "fonts": [],
            "extracted_elements": 0
        })
        
        # Add content_elements if available (could extract from data_extraction)
        structured.setdefault("content_elements", [])
        
        return structured
