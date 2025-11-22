"""Mapping validator service for validating generated mappings."""

from __future__ import annotations

import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from ...services.integration.external_api_client import ExternalAIClient
from ...services.manipulation.substring_manipulator import SubstringManipulator
from ...services.validation.gpt5_validation_service import GPT5ValidationService, ValidationResult
from ...utils.logging import get_logger
from .gpt5_config import VALIDATION_MODEL, VALIDATION_TIMEOUT


class MappingSuggestionError(ValueError):
    """Raised when a mapping cannot be applied but provides a follow-up hint."""

    def __init__(self, message: str, suggestion: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.suggestion = suggestion or {}


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
        run_id: Optional[str] = None,
        latex_text: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate mappings in order until first success.
        
        Returns:
            Tuple of (first_valid_mapping, validation_logs)
        """
        validation_logs = []
        
        for idx, mapping in enumerate(mappings):
            try:
                result, hint = self._validate_single_mapping(
                    question_text=question_text,
                    question_type=question_type,
                    gold_answer=gold_answer,
                    options_data=options_data,
                    mapping=mapping,
                    mapping_index=idx,
                    run_id=run_id,
                    latex_text=latex_text,
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
                if hint:
                    validation_log["suggestion"] = hint
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
                error_entry = {
                    "mapping_index": idx,
                    "timestamp": time.time(),
                    "status": "error",
                    "error": str(e)
                }
                suggestion = getattr(e, "suggestion", None)
                if suggestion:
                    error_entry["suggestion"] = suggestion
                validation_logs.append(error_entry)
        
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
        run_id: Optional[str] = None,
        latex_text: Optional[str] = None,
    ) -> Tuple[ValidationResult, Optional[Dict[str, Any]]]:
        """Validate a single mapping."""
        modified_text = self._apply_mapping_to_question(
            question_text=question_text,
            mapping=mapping,
            latex_text=latex_text,
        )
        
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
        
        suggestion = self._build_validation_suggestion(
            validation_result=validation_result,
            mapping=mapping,
            options_data=options_data,
            question_type=question_type,
            gold_answer=gold_answer,
        )

        return validation_result, suggestion
    
    def _apply_mapping_to_question(
        self,
        question_text: str,
        mapping: Dict[str, Any],
        latex_text: Optional[str] = None,
    ) -> str:
        """Apply a mapping to the plain-text question, using normalized search."""
        original = mapping.get("original_substring", "")
        replacement = mapping.get("replacement_substring", "")
        if not original:
            raise MappingSuggestionError(
                "Original substring is empty",
                suggestion=self._build_suggestion_payload(question_text, original),
            )

        # Attempt exact match first
        if original in question_text:
            return question_text.replace(original, replacement, 1)

        stripped = original.strip()
        if stripped and stripped in question_text:
            return question_text.replace(stripped, replacement, 1)

        index_info = self._find_substring_with_normalization(question_text, original)
        if index_info:
            start, end = index_info
            return question_text[:start] + replacement + question_text[end:]

        suggestion = self._build_suggestion_payload(question_text, original)
        raise MappingSuggestionError(
            f"Original substring '{original}' not found in question text",
            suggestion=suggestion,
        )

    def _build_validation_suggestion(
        self,
        *,
        validation_result: ValidationResult,
        mapping: Dict[str, Any],
        options_data: Optional[Dict[str, str]],
        question_type: str,
        gold_answer: str,
    ) -> Optional[Dict[str, Any]]:
        """Translate validation feedback into actionable retry guidance."""
        if validation_result.is_valid:
            return None

        suggestion: Dict[str, Any] = {}

        test_answer = (validation_result.test_answer or "").strip()
        gold_label = self._normalize_answer_token(gold_answer, options_data)
        test_label = self._normalize_answer_token(test_answer, options_data)
        target_option = (mapping.get("target_wrong_answer") or "").strip()
        target_label = self._normalize_answer_token(target_option, options_data)
        target_text = (options_data or {}).get(target_option) if options_data and target_option else None

        if gold_label and test_label and gold_label == test_label:
            instructions = self._build_flip_instruction(
                question_type=question_type,
                gold_label=gold_label,
                target_label=target_label or target_option,
                target_text=target_text,
                options_data=options_data,
            )
            suggestion.update(
                {
                    "reason": "answer_did_not_change",
                    "instructions": instructions,
                    "observed_answer": test_answer or gold_answer,
                }
            )
            if target_option:
                suggestion["target_option"] = target_option
            if target_text:
                suggestion["target_option_text"] = target_text
            return suggestion if suggestion.get("instructions") else None

        return None

    def _build_suggestion_payload(self, question_text: str, original: str) -> Dict[str, Any]:
        """Create a suggestion payload to guide a retry."""
        suggestion: Dict[str, Any] = {}
        if original:
            suggestion["missing_substring"] = original

        answer_phrase = self._extract_answer_phrase(question_text)
        if answer_phrase:
            suggestion["suggested_substring"] = answer_phrase

        return suggestion

    def _extract_answer_phrase(self, text: str) -> Optional[str]:
        """Extract the final quoted phrase from the question text."""
        if not text:
            return None
        matches = re.findall(r"'([^']+)'", text)
        return matches[-1] if matches else None

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

    def _normalize_with_index(self, text: str) -> Tuple[str, List[int]]:
        """Return normalized text (NFKC) and index map to original positions."""
        norm_chars: List[str] = []
        index_map: List[int] = []
        for idx, char in enumerate(text):
            norm_char = unicodedata.normalize("NFKC", char)
            norm_chars.append(norm_char)
            for _ in norm_char:
                index_map.append(idx)
        normalized = "".join(norm_chars)
        return normalized, index_map

    def _find_substring_with_normalization(
        self,
        text: str,
        substring: str,
    ) -> Optional[Tuple[int, int]]:
        """Locate substring in text using NFKC normalization."""
        if not text or not substring:
            return None
        norm_text, index_map = self._normalize_with_index(text)
        norm_sub, _ = self._normalize_with_index(substring)
        search_text = norm_text.lower()
        search_sub = norm_sub.lower()
        idx = search_text.find(search_sub)
        if idx == -1:
            return None
        start = index_map[idx]
        end_index = idx + len(norm_sub) - 1
        if end_index >= len(index_map):
            return None
        end = index_map[end_index] + 1
        return start, end

    def _normalize_answer_token(
        self,
        answer: Optional[str],
        options_data: Optional[Dict[str, str]],
    ) -> str:
        """Normalize an answer string to a comparable token."""
        if not answer:
            return ""
        answer_str = str(answer).strip()
        if not answer_str:
            return ""

        if options_data:
            normalized_keys = {str(k).strip().upper(): str(k).strip().upper() for k in options_data.keys()}
            upper_answer = answer_str.upper()
            if upper_answer in normalized_keys:
                return normalized_keys[upper_answer]

            # Handle leading key with punctuation (e.g., "B.", "C)")
            leading_match = re.match(r"^([A-Z])[\).:\- ]?", upper_answer)
            if leading_match:
                key = leading_match.group(1)
                if key in normalized_keys:
                    return key

            # Match option text directly
            lower_answer = answer_str.lower()
            for key, value in options_data.items():
                if lower_answer == (value or "").strip().lower():
                    return str(key).strip().upper()

        lowered = answer_str.lower()
        if lowered in {"true", "false"}:
            return lowered

        return answer_str.strip()

    def _format_option_reference(
        self,
        label: Optional[str],
        options_data: Optional[Dict[str, str]],
        *,
        fallback_text: Optional[str] = None,
    ) -> str:
        """Convert an answer label into a user-facing description."""
        if not label and not fallback_text:
            return "the alternate option"

        if label:
            normalized_label = str(label).strip()
        else:
            normalized_label = ""

        if normalized_label in {"true", "false"}:
            return normalized_label.capitalize()

        if options_data and normalized_label and len(normalized_label) == 1:
            option_text = options_data.get(normalized_label)
            if option_text:
                return f"option {normalized_label} ({option_text})"
            return f"option {normalized_label}"

        if fallback_text:
            return fallback_text

        return normalized_label or "the alternate option"

    def _build_flip_instruction(
        self,
        *,
        question_type: str,
        gold_label: Optional[str],
        target_label: Optional[str],
        target_text: Optional[str],
        options_data: Optional[Dict[str, str]],
    ) -> str:
        """Create human-readable guidance for forcing a flipped answer."""
        gold_display = self._format_option_reference(gold_label, options_data)

        if question_type.lower() == "true_false":
            target_display = target_text or (
                "False" if (gold_label or "").lower() == "true" else "True"
            )
            return (
                f"The modified statement still evaluates to {gold_display}. "
                f"Change the claim so the correct answer becomes {target_display}."
            )

        target_display = self._format_option_reference(
            target_label,
            options_data,
            fallback_text=target_text,
        )
        return (
            f"The validator saw the model stick with {gold_display}. "
            f"Adjust the replacement so the question now drives the model toward {target_display}."
        )

    
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
