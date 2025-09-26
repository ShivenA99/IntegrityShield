"""
Attack Orchestrator Service

Central coordinator for all attack strategies in the refactored architecture.
Handles Prevention and Detection modes with intelligent fallback strategies.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from .attack_service import AttackConfig, AttackMode, QuestionAttackResult

logger = logging.getLogger(__name__)

class AttackOrchestrator:
    """
    Central service for coordinating all attack strategies.
    
    This service:
    1. Receives attack configuration from API
    2. Delegates to appropriate attack services
    3. Coordinates mixed PDF generation
    4. Tracks attack results and metadata
    """
    
    def __init__(self):
        self.prevention_service = None  # Will be initialized lazily
        self.detection_service = None   # Will be initialized lazily
        self.mixed_pdf_renderer = None # Will be initialized lazily
        
        logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Initialized attack orchestrator")
    
    def execute_attack(
        self, 
        questions: List[Dict[str, Any]], 
        config: AttackConfig,
        assessment_dir: Path,
        original_pdf_path: Path,
        ocr_doc: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute attack strategy based on configuration.
        
        Args:
            questions: List of parsed questions from OCR
            config: Attack configuration (mode + optional sub-type)
            assessment_dir: Directory for this assessment
            original_pdf_path: Path to original PDF
            ocr_doc: Complete OCR document structure
            
        Returns:
            Dict containing:
            - attack_results: List[QuestionAttackResult]
            - attacked_pdf_path: Path to generated PDF
            - metadata: Attack execution metadata
        """
        logger.info(
            "[REFACTOR][ATTACK_ORCHESTRATOR] Executing %s attack for %d questions",
            config.mode.value, len(questions)
        )
        
        if config.mode == AttackMode.PREVENTION:
            return self._execute_prevention_attack(questions, config, assessment_dir, original_pdf_path, ocr_doc)
        elif config.mode == AttackMode.DETECTION:
            return self._execute_detection_attack(questions, config, assessment_dir, original_pdf_path, ocr_doc)
        else:
            raise ValueError(f"Unknown attack mode: {config.mode}")
    
    def _execute_prevention_attack(
        self, 
        questions: List[Dict[str, Any]], 
        config: AttackConfig,
        assessment_dir: Path,
        original_pdf_path: Path,
        ocr_doc: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute prevention attack with hidden text injection."""
        logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Starting prevention attack")
        
        # Lazy import to avoid circular dependencies
        if self.prevention_service is None:
            from .prevention_attack_service import PreventionAttackService
            self.prevention_service = PreventionAttackService()
        
        # Execute prevention strategy
        attack_results = self.prevention_service.execute_prevention_attack(questions, config)
        
        # Generate attacked PDF
        attacked_pdf_path = self._generate_attacked_pdf(
            attack_results, assessment_dir, original_pdf_path, ocr_doc, "prevention"
        )
        
        logger.info(
            "[REFACTOR][ATTACK_ORCHESTRATOR] Prevention attack completed. PDF: %s", 
            attacked_pdf_path
        )
        
        return {
            "attack_results": attack_results,
            "attacked_pdf_path": attacked_pdf_path,
            "metadata": {
                "attack_mode": config.mode.value,
                "prevention_sub_type": config.prevention_sub_type.value if config.prevention_sub_type else None,
                "total_questions": len(questions),
                "success_rate": 1.0  # Prevention always succeeds with hidden text
            }
        }
    
    def _execute_detection_attack(
        self, 
        questions: List[Dict[str, Any]], 
        config: AttackConfig,
        assessment_dir: Path,
        original_pdf_path: Path,
        ocr_doc: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute detection attack with Code Glyph primary + Hidden Text fallback."""
        logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Starting detection attack")
        
        # Lazy import to avoid circular dependencies
        if self.detection_service is None:
            from .detection_attack_service import DetectionAttackService
            self.detection_service = DetectionAttackService()
        
        # Execute detection strategy per question
        attack_results = self.detection_service.execute_detection_attack(questions, ocr_doc)
        
        # Generate mixed attack PDF
        attacked_pdf_path = self._generate_attacked_pdf(
            attack_results, assessment_dir, original_pdf_path, ocr_doc, "detection"
        )
        
        # Calculate success rates
        code_glyph_success = sum(1 for r in attack_results if r.attack_method == "code_glyph")
        hidden_text_fallback = sum(1 for r in attack_results if r.attack_method == "hidden_text")
        
        logger.info(
            "[REFACTOR][ATTACK_ORCHESTRATOR] Detection attack completed. "
            "Code Glyph: %d/%d, Hidden Text fallback: %d/%d. PDF: %s",
            code_glyph_success, len(questions), 
            hidden_text_fallback, len(questions),
            attacked_pdf_path
        )
        
        return {
            "attack_results": attack_results,
            "attacked_pdf_path": attacked_pdf_path,
            "metadata": {
                "attack_mode": config.mode.value,
                "total_questions": len(questions),
                "code_glyph_success": code_glyph_success,
                "hidden_text_fallback": hidden_text_fallback,
                "code_glyph_success_rate": code_glyph_success / len(questions) if questions else 0.0
            }
        }
    
    def _generate_attacked_pdf(
        self,
        attack_results: List[QuestionAttackResult],
        assessment_dir: Path,
        original_pdf_path: Path,
        ocr_doc: Dict[str, Any],
        attack_mode: str
    ) -> Path:
        """Generate attacked PDF using mixed renderer."""
        logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Generating attacked PDF")
        
        # Lazy import to avoid circular dependencies
        if self.mixed_pdf_renderer is None:
            from ..rendering.mixed_pdf_renderer import MixedPdfRenderer
            self.mixed_pdf_renderer = MixedPdfRenderer()
        
        attacked_pdf_path = assessment_dir / "attacked.pdf"
        
        self.mixed_pdf_renderer.render_mixed_attack_pdf(
            attack_results=attack_results,
            original_pdf_path=original_pdf_path,
            ocr_doc=ocr_doc,
            output_path=attacked_pdf_path,
            attack_mode=attack_mode
        )
        
        logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Generated attacked PDF: %s", attacked_pdf_path)

        # Optional: parse original vs attacked PDFs for debugging differences
        try:
            from .pdf_diff_debugger import diff_pdfs
            orig_pdf = original_pdf_path
            attacked_pdf = attacked_pdf_path
            logger.info("[REFACTOR][ATTACK_ORCHESTRATOR] Running PDF diff debugger")
            diff_result = diff_pdfs(Path(orig_pdf), Path(attacked_pdf))
            logger.debug("[REFACTOR][ATTACK_ORCHESTRATOR] PDF diff summary: %s", diff_result.get("summary"))
        except Exception as e:
            logger.warning("[REFACTOR][ATTACK_ORCHESTRATOR] PDF diff failed: %s", e)
        return attacked_pdf_path