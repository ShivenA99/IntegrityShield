"""Mapping validator service for validating generated mappings."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from ...services.integration.external_api_client import ExternalAIClient
from ...services.manipulation.substring_manipulator import SubstringManipulator
from ...services.validation.gpt5_validation_service import GPT5ValidationService, ValidationResult
from ...utils.logging import get_logger
from .gpt5_config import VALIDATION_MODEL, VALIDATION_TIMEOUT


class MappingValidator:
    """Validator for generated mappings."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.manipulator = SubstringManipulator()
        self.validator = GPT5ValidationService()
        self.ai_client = ExternalAIClient()
    
    def validate_mapping_sequence(
        self,
        question_text: str,
        question_type: str,
        gold_answer: str,
        options_data: Optional[Dict[str, str]],
        mappings: List[Dict[str, Any]],
        run_id: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate mappings in order until first success.
        
        Returns:
            Tuple of (first_valid_mapping, validation_logs)
        """
        validation_logs = []
        
        for idx, mapping in enumerate(mappings):
            try:
                result = self._validate_single_mapping(
                    question_text=question_text,
                    question_type=question_type,
                    gold_answer=gold_answer,
                    options_data=options_data,
                    mapping=mapping,
                    mapping_index=idx,
                    run_id=run_id
                )
                
                validation_log = {
                    "mapping_index": idx,
                    "timestamp": time.time(),
                    "status": "success" if result.is_valid else "failed",
                    "validation_result": {
                        "is_valid": result.is_valid,
                        "confidence": result.confidence,
                        "deviation_score": result.deviation_score,
                        "reasoning": result.reasoning,
                        "target_matched": result.target_matched
                    }
                }
                validation_logs.append(validation_log)
                
                if result.is_valid:
                    self.logger.info(
                        f"Mapping {idx} validated successfully",
                        run_id=run_id,
                        question_type=question_type,
                        confidence=result.confidence
                    )
                    return mapping, validation_logs
                else:
                    self.logger.info(
                        f"Mapping {idx} validation failed",
                        run_id=run_id,
                        question_type=question_type,
                        reason=result.reasoning
                    )
            except Exception as e:
                self.logger.warning(
                    f"Validation error for mapping {idx}: {e}",
                    run_id=run_id
                )
                validation_logs.append({
                    "mapping_index": idx,
                    "timestamp": time.time(),
                    "status": "error",
                    "error": str(e)
                })
        
        # No valid mapping found
        return None, validation_logs
    
    def _validate_single_mapping(
        self,
        question_text: str,
        question_type: str,
        gold_answer: str,
        options_data: Optional[Dict[str, str]],
        mapping: Dict[str, Any],
        mapping_index: int,
        run_id: Optional[str] = None
    ) -> ValidationResult:
        """Validate a single mapping."""
        # Apply mapping to question text
        modified_text = self._apply_mapping_to_question(question_text, mapping)
        
        # Get AI model response to modified question
        test_answer = self._get_model_response(
            modified_text=modified_text,
            question_type=question_type,
            options_data=options_data,
            run_id=run_id
        )
        
        # Extract target information from mapping
        target_option = mapping.get("target_wrong_answer")
        target_option_text = None
        if target_option and options_data:
            target_option_text = options_data.get(target_option)
        
        # Validate using GPT5ValidationService
        validation_result = self.validator.validate_answer_deviation(
            question_text=modified_text,
            question_type=question_type,
            gold_answer=gold_answer,
            test_answer=test_answer,
            options_data=options_data,
            target_option=target_option,
            target_option_text=target_option_text,
            run_id=run_id
        )
        
        return validation_result
    
    def _apply_mapping_to_question(
        self,
        question_text: str,
        mapping: Dict[str, Any]
    ) -> str:
        """Apply a single mapping to question text.
        
        Note: Positions in mapping are relative to latex_stem_text, but we're applying
        to plain text (stem_text). So we use string replacement instead of positional matching.
        """
        original = mapping.get("original_substring", "")
        replacement = mapping.get("replacement_substring", "")
        
        # For validation, we use string replacement since positions are relative to LaTeX
        # but we're validating against plain text. The positions are only used for LaTeX matching.
        if not original:
            raise ValueError("Original substring is empty")
        
        # Try to find original in question text (may need normalization)
        # First try exact match
        if original in question_text:
            modified = question_text.replace(original, replacement, 1)
            return modified
        
        # Try normalized match (remove LaTeX commands)
        normalized_original = self._normalize_text(original)
        normalized_question = self._normalize_text(question_text)
        
        if normalized_original in normalized_question:
            # Find position in normalized text
            pos = normalized_question.find(normalized_original)
            if pos != -1:
                # Map back to original text (approximate)
                # This is a fallback - ideally original should match exactly
                modified = question_text.replace(original, replacement, 1) if original in question_text else question_text
                return modified
        
        # If still not found, try to find a substring match
        if original.strip() in question_text:
            modified = question_text.replace(original.strip(), replacement, 1)
            return modified
        
        raise ValueError(f"Original substring '{original}' not found in question text")
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text by removing LaTeX commands."""
        import re
        normalized = text
        # Remove common LaTeX commands
        normalized = re.sub(r"\\textbf\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\textit\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\emph\{([^}]*)\}", r"\1", normalized)
        normalized = re.sub(r"\\text\{([^}]*)\}", r"\1", normalized)
        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()
    
    def _get_model_response(
        self,
        modified_text: str,
        question_type: str,
        options_data: Optional[Dict[str, str]],
        run_id: Optional[str] = None
    ) -> str:
        """Get AI model response to modified question."""
        # Build prompt
        prompt = f"Question: {modified_text}\n"
        if options_data:
            prompt += "Options:\n"
            for key, value in options_data.items():
                prompt += f"{key}. {value}\n"
        prompt += "\nReturn only the final answer (e.g., option letter or short text)."
        
        try:
            result = self.ai_client.call_model(
                provider=VALIDATION_MODEL,
                payload={"prompt": prompt}
            )
            test_answer = (result or {}).get("response", "").strip()
            
            if not test_answer or test_answer == "simulated-response":
                # Fallback for MCQ
                if question_type in {"mcq_single", "mcq_multi", "true_false"} and options_data:
                    gold_clean = (options_data.get("A") or "").strip().lower()
                    for opt_key in options_data.keys():
                        key_clean = str(opt_key).strip().lower()
                        if key_clean != gold_clean:
                            test_answer = str(opt_key)
                            break
                    if not test_answer and options_data:
                        test_answer = str(next(iter(options_data.keys())))
                else:
                    test_answer = "inconclusive"
            
            return test_answer
        except Exception as e:
            self.logger.warning(f"Failed to get model response: {e}", run_id=run_id)
            # Return fallback answer
            if question_type in {"mcq_single", "mcq_multi", "true_false"} and options_data:
                return str(next(iter(options_data.keys())))
            return "inconclusive"

