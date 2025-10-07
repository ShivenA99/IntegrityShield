from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List

from .openai_vision_client import OpenAIVisionClient
from .mistral_ocr_client import MistralOCRClient
from .base_ai_client import AIExtractionResult
from ...utils.logging import get_logger
from ..developer.live_logging_service import live_logging_service


class AIClientOrchestrator:
    """Orchestrates multiple AI clients for comprehensive question extraction."""

    def __init__(self):
        self.openai_client = OpenAIVisionClient()
        self.mistral_client = MistralOCRClient()
        self.logger = get_logger(__name__)

    def extract_questions_comprehensive(
        self,
        pdf_path: Path,
        pymupdf_data: Dict[str, Any],
        run_id: str,
        parallel: bool = True
    ) -> AIExtractionResult:
        """
        Extract questions using the configured AI sources and return the most reliable result.

        Args:
            pdf_path: Path to the PDF file
            pymupdf_data: Raw extraction data from PyMuPDF
            run_id: Pipeline run ID for logging
            parallel: Whether to run extractions in parallel

        Returns:
            Highest confidence extraction result from the available sources
        """
        start_time = time.perf_counter()

        # Check which clients are configured
        available_clients = self._get_available_clients()
        live_logging_service.emit(
            run_id,
            "ai_orchestrator",
            "INFO",
            "Starting comprehensive AI extraction",
            context={
                "sources": list(available_clients.keys()),
                "parallel": parallel
            }
        )

        if not available_clients:
            return AIExtractionResult(
                source="ai_orchestrator",
                confidence=0.0,
                questions=[],
                error="No AI clients are properly configured"
            )

        try:
            # Extract from all available sources
            if parallel and len(available_clients) > 1:
                extraction_results = self._extract_parallel(pdf_path, run_id, available_clients)
            else:
                extraction_results = self._extract_sequential(pdf_path, run_id, available_clients)

            best_result = self._select_best_result(extraction_results)
            best_result.raw_response = best_result.raw_response or {}
            best_result.raw_response['orchestration'] = {
                'decision_strategy': 'best_available_source',
                'selected_source': best_result.source,
                'available_sources': list(extraction_results.keys()),
                'extraction_results': {
                    source: {
                        'questions_count': len(result.questions),
                        'confidence': result.confidence,
                        'processing_time_ms': result.processing_time_ms,
                        'error': result.error,
                    }
                    for source, result in extraction_results.items()
                },
                'total_processing_time_ms': int((time.perf_counter() - start_time) * 1000),
                'clients_used': list(extraction_results.keys())
            }

            return best_result

        except Exception as e:
            self.logger.error(f"AI orchestration failed: {e}", run_id=run_id, error=str(e))
            live_logging_service.emit(
                run_id,
                "ai_orchestrator",
                "ERROR",
                f"Orchestration failed: {e}"
            )

            return AIExtractionResult(
                source="ai_orchestrator",
                confidence=0.0,
                questions=[],
                error=str(e)
            )

    def _get_available_clients(self) -> Dict[str, Any]:
        """Get configured AI clients."""
        clients = {}

        if self.openai_client.is_configured():
            clients['openai_vision'] = self.openai_client

        if self.mistral_client.is_configured():
            clients['mistral_ocr'] = self.mistral_client

        return clients

    def _extract_parallel(
        self,
        pdf_path: Path,
        run_id: str,
        available_clients: Dict[str, Any]
    ) -> Dict[str, AIExtractionResult]:
        """Extract questions in parallel from all sources."""
        results = {}

        with ThreadPoolExecutor(max_workers=len(available_clients)) as executor:
            # Submit extraction tasks
            future_to_source = {}

            for source, client in available_clients.items():
                future = executor.submit(
                    client.extract_questions_from_pdf,
                    pdf_path,
                    run_id
                )
                future_to_source[future] = source

            # Collect results as they complete
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    result = future.result(timeout=300)  # 5 minute timeout per client
                    results[source] = result

                    live_logging_service.emit(
                        run_id,
                        "ai_orchestrator",
                        "INFO",
                        f"{source} extraction completed",
                        context={
                            "questions_found": len(result.questions),
                            "confidence": result.confidence,
                            "processing_time_ms": result.processing_time_ms
                        }
                    )

                except Exception as e:
                    self.logger.warning(f"{source} extraction failed: {e}")
                    live_logging_service.emit(
                        run_id,
                        "ai_orchestrator",
                        "WARNING",
                        f"{source} extraction failed: {e}"
                    )

        return results

    def _extract_sequential(
        self,
        pdf_path: Path,
        run_id: str,
        available_clients: Dict[str, Any]
    ) -> Dict[str, AIExtractionResult]:
        """Extract questions sequentially from all sources."""
        results = {}

        for source, client in available_clients.items():
            try:
                live_logging_service.emit(
                    run_id,
                    "ai_orchestrator",
                    "INFO",
                    f"Starting {source} extraction"
                )

                result = client.extract_questions_from_pdf(pdf_path, run_id)
                results[source] = result

                live_logging_service.emit(
                    run_id,
                    "ai_orchestrator",
                    "INFO",
                    f"{source} extraction completed",
                    context={
                        "questions_found": len(result.questions),
                        "confidence": result.confidence
                    }
                )

            except Exception as e:
                self.logger.warning(f"{source} extraction failed: {e}")
                live_logging_service.emit(
                    run_id,
                    "ai_orchestrator",
                    "WARNING",
                    f"{source} extraction failed: {e}"
                )

        return results

    def _select_best_result(self, extraction_results: Dict[str, AIExtractionResult]) -> AIExtractionResult:
        """Select the most reliable extraction result among available sources."""
        if not extraction_results:
            return AIExtractionResult(
                source="ai_orchestrator",
                confidence=0.0,
                questions=[],
                error="No extraction results available"
            )

        # Score each result
        scored_results = []
        for source, result in extraction_results.items():
            score = self._calculate_result_score(result)
            scored_results.append((score, source, result))

        # Return best scored result
        scored_results.sort(reverse=True)
        best_score, best_source, best_result = scored_results[0]

        self.logger.info(
            f"Selected {best_source} as best result with score {best_score}",
            results_scores=[(score, source) for score, source, _ in scored_results]
        )

        return best_result

    def _calculate_result_score(self, result: AIExtractionResult) -> float:
        """Calculate score for ranking results."""
        if not result or result.error:
            return 0.0

        # Base score from confidence and question count
        base_score = result.confidence * min(len(result.questions), 10) / 10

        # Bonus for having complete questions with options
        complete_questions = sum(
            1 for q in result.questions
            if q.get('stem_text') and (q.get('options') or q.get('question_type') in ['short_answer', 'fill_blank'])
        )

        completeness_bonus = (complete_questions / max(len(result.questions), 1)) * 0.2

        # Source preference bonus
        source_bonus = {
            'openai_vision': 0.1,
            'mistral_ocr': 0.05,
        }.get(result.source, 0.0)

        return base_score + completeness_bonus + source_bonus

    async def test_all_clients(self, run_id: str) -> Dict[str, Dict[str, Any]]:
        """Test all AI clients for connectivity and configuration."""
        test_results = {}

        clients_to_test = {
            'openai_vision': self.openai_client,
            'mistral_ocr': self.mistral_client,
        }

        for client_name, client in clients_to_test.items():
            test_result = {
                'configured': client.is_configured(),
                'available': False,
                'error': None
            }

            if client.is_configured():
                try:
                    # Simple connectivity test
                    if hasattr(client, '_get_openai_client'):
                        # Test OpenAI clients
                        test_client = client._get_openai_client()
                        test_result['available'] = test_client is not None
                    elif hasattr(client, 'api_key'):
                        # Test Mistral client
                        test_result['available'] = bool(client.api_key)
                    else:
                        test_result['available'] = True

                except Exception as e:
                    test_result['error'] = str(e)

            test_results[client_name] = test_result

        self.logger.info(f"AI client test results: {test_results}", run_id=run_id)
        return test_results
