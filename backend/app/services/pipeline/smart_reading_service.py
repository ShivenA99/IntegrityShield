from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List

import fitz
from ...models import PipelineRun
from ...services.data_management.file_manager import FileManager
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.ai_clients.ai_client_orchestrator import AIClientOrchestrator
from ...services.developer.live_logging_service import live_logging_service
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now
from ...services.pipeline.enhancement_methods.span_extractor import collect_span_records


class SmartReadingService:
    def __init__(self) -> None:
        self.logger = get_logger(__name__)
        self.file_manager = FileManager()
        self.structured_manager = StructuredDataManager()
        self.ai_orchestrator = AIClientOrchestrator()

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
            "Starting enhanced multi-source PDF processing",
            context={"pdf_path": str(pdf_path)}
        )

        # Step 1: Traditional PyMuPDF extraction (baseline)
        pymupdf_data = self._extract_pymupdf_data(pdf_path, run_id)

        # Step 2: AI-powered question extraction
        ai_result = self.ai_orchestrator.extract_questions_comprehensive(
            pdf_path, pymupdf_data, run_id, parallel=True
        )

        # Step 3: Build comprehensive structured data
        structured = self._build_enhanced_structured_data(
            run_id, pdf_path, pymupdf_data, ai_result
        )

        self.structured_manager.save(run_id, structured)

        live_logging_service.emit(
            run_id,
            "smart_reading",
            "INFO",
            "Enhanced PDF processing completed",
            context={
                "pymupdf_elements": len(pymupdf_data.get("content_elements", [])),
                "ai_questions_found": len(ai_result.questions),
                "ai_confidence": ai_result.confidence,
                "ai_sources": ai_result.raw_response.get("orchestration", {}).get("clients_used", []) if ai_result.raw_response else []
            }
        )

        return {
            "pages": pymupdf_data.get("document", {}).get("pages", 0),
            "elements_extracted": len(pymupdf_data.get("content_elements", [])),
            "images_extracted": len(pymupdf_data.get("assets", {}).get("images", [])),
            "ai_questions_found": len(ai_result.questions),
            "ai_confidence": ai_result.confidence,
            "ai_processing_time_ms": ai_result.processing_time_ms,
        }

    def _extract_pymupdf_data(self, pdf_path: Path, run_id: str) -> Dict[str, Any]:
        """Extract baseline data using PyMuPDF."""
        live_logging_service.emit(run_id, "smart_reading", "INFO", "Extracting PyMuPDF baseline data")

        doc = fitz.open(pdf_path)
        content_elements: List[Dict[str, Any]] = []
        images: List[Dict[str, Any]] = []
        span_index: List[Dict[str, Any]] = []
        fonts = set()

        page_count = doc.page_count

        for page_index in range(page_count):
            page = doc[page_index]
            text_dict = page.get_text("dict")

            for block in text_dict.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        content_elements.append(
                            {
                                "type": "text",
                                "content": span.get("text"),
                                "page": page_index + 1,
                                "bbox": span.get("bbox"),
                                "font": span.get("font"),
                                "size": span.get("size"),
                            }
                        )
                        fonts.add(span.get("font"))

            # Extract images
            for image_index, (xref, *_rest) in enumerate(page.get_images(), start=1):
                base_image = doc.extract_image(xref)
                if not base_image:
                    continue
                image_bytes = base_image["image"]
                ext = base_image.get("ext", "png")
                filename = f"page{page_index+1}_img{image_index}.{ext}"
                asset_path = self.file_manager.store_asset(run_id, filename, image_bytes)

                images.append(
                    {
                        "filename": filename,
                        "path": str(asset_path),
                        "page": page_index + 1,
                        "width": base_image.get("width"),
                        "height": base_image.get("height"),
                    }
                )

            # Collect detailed span metadata for downstream span selection
            span_records = collect_span_records(page, page_index)
            page_spans: List[Dict[str, Any]] = []
            for record in span_records:
                span_id = (
                    f"page{page_index}:block{record.block_index}:"
                    f"line{record.line_index}:span{record.span_index}"
                )
                raw_text = record.text or ""
                prompt_text = raw_text.replace("\n", " ").strip()
                if len(prompt_text) > 320:
                    prompt_text = prompt_text[:317] + "..."
                bbox = [float(record.bbox[0]), float(record.bbox[1]), float(record.bbox[2]), float(record.bbox[3])]
                quad = [
                    bbox[0], bbox[1],
                    bbox[2], bbox[1],
                    bbox[2], bbox[3],
                    bbox[0], bbox[3],
                ]
                page_spans.append(
                    {
                        "id": span_id,
                        "page": page_index + 1,
                        "block": record.block_index,
                        "line": record.line_index,
                        "span": record.span_index,
                        "text": raw_text,
                        "prompt_text": prompt_text,
                        "bbox": bbox,
                        "quad": quad,
                        "font": record.font,
                        "size": record.font_size,
                    }
                )

            span_index.append({"page": page_index + 1, "spans": page_spans})

        doc.close()

        return {
            "document": {
                "source_path": str(pdf_path),
                "filename": pdf_path.name,
                "pages": page_count,
            },
            "assets": {
                "images": images,
                "fonts": sorted(fonts),
                "extracted_elements": len(content_elements),
            },
            "content_elements": content_elements,
            "span_index": span_index,
        }

    def _build_enhanced_structured_data(
        self,
        run_id: str,
        pdf_path: Path,
        pymupdf_data: Dict[str, Any],
        ai_result
    ) -> Dict[str, Any]:
        """Build comprehensive structured data combining all sources."""
        structured = self.structured_manager.load(run_id)

        # Update pipeline metadata
        structured.setdefault("pipeline_metadata", {})
        structured["pipeline_metadata"].update(
            {
                "current_stage": "smart_reading",
                "stages_completed": ["smart_reading"],
                "last_updated": isoformat(utc_now()),
                "ai_extraction_enabled": True,
                "ai_sources_used": ai_result.raw_response.get("orchestration", {}).get("clients_used", []) if ai_result.raw_response else []
            }
        )

        # Add PyMuPDF baseline data
        structured["document"] = pymupdf_data["document"]
        structured["assets"] = pymupdf_data["assets"]
        structured["content_elements"] = pymupdf_data["content_elements"]
        structured["pymupdf_span_index"] = pymupdf_data.get("span_index", [])

        # Add AI extraction results
        structured["ai_extraction"] = {
            "source": ai_result.source,
            "confidence": ai_result.confidence,
            "questions_found": len(ai_result.questions),
            "processing_time_ms": ai_result.processing_time_ms,
            "cost_cents": ai_result.cost_cents,
            "error": ai_result.error,
            "raw_response": ai_result.raw_response
        }

        # Store AI-detected questions (will be processed by content discovery)
        structured["ai_questions"] = ai_result.questions

        return structured
