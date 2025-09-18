"""
Detection Attack Service

Handles detection attacks with Code Glyph primary strategy and Hidden Text fallback.
Detection attacks aim to make LLMs provide wrong answers to questions.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .attack_service import QuestionAttackResult

logger = logging.getLogger(__name__)

class DetectionAttackService:
    """
    Service for executing detection attacks with intelligent fallback strategy.
    
    Detection strategy per question:
    1. Generate V3 Code Glyph entities (entity-level, not sentence)
    2. Validate with LLM verification call  
    3. If validation fails → try alternatives from verification response
    4. If all alternatives fail → fallback to Hidden Text detection
    5. Track which method succeeded for this question
    """
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.use_validation = self.openai_api_key is not None
        
        # Force CG_OVERLAY_MODE=1 for entity-level rendering
        os.environ["CG_OVERLAY_MODE"] = "1"
        
        logger.info(
            "[REFACTOR][DETECTION] Initialized detection attack service "
            "(validation=%s, overlay_mode=1)",
            self.use_validation
        )
    
    def execute_detection_attack(
        self, 
        questions: List[Dict[str, Any]], 
        ocr_doc: Dict[str, Any]
    ) -> List[QuestionAttackResult]:
        """
        Execute detection attack for all questions with fallback strategy.
        
        Args:
            questions: List of questions from OCR
            ocr_doc: Complete OCR document structure
            
        Returns:
            List of QuestionAttackResult objects
        """
        logger.info(
            "[REFACTOR][DETECTION] Executing detection attack for %d questions",
            len(questions)
        )
        
        attack_results = []
        code_glyph_success = 0
        hidden_text_fallback = 0
        
        for i, question in enumerate(questions):
            try:
                result = self._execute_per_question_detection(question, ocr_doc)
                attack_results.append(result)
                
                if result.attack_method == "code_glyph":
                    code_glyph_success += 1
                elif result.attack_method == "hidden_text":
                    hidden_text_fallback += 1
                
                logger.debug(
                    "[REFACTOR][DETECTION] Question %d (%s): method=%s, success=%s",
                    i + 1, question.get("q_number", "unknown"), 
                    result.attack_method, result.success
                )
                
            except Exception as e:
                logger.error(
                    "[REFACTOR][DETECTION] Failed to process question %d: %s",
                    i + 1, str(e)
                )
                # Create fallback result
                result = self._create_fallback_result(question, str(e))
                attack_results.append(result)
                hidden_text_fallback += 1
        
        logger.info(
            "[REFACTOR][DETECTION] Detection attack completed: "
            "Code Glyph=%d/%d, Hidden Text fallback=%d/%d",
            code_glyph_success, len(questions),
            hidden_text_fallback, len(questions)
        )
        
        return attack_results
    
    def _execute_per_question_detection(
        self, 
        question: Dict[str, Any], 
        ocr_doc: Dict[str, Any]
    ) -> QuestionAttackResult:
        """
        Execute detection attack for a single question with fallback strategy.
        
        Args:
            question: Question dictionary
            ocr_doc: OCR document structure
            
        Returns:
            QuestionAttackResult for this question
        """
        q_number = question.get("q_number", "unknown")
        
        logger.debug("[REFACTOR][DETECTION] Processing question %s", q_number)
        
        # Step 1: Attempt Code Glyph attack
        code_glyph_result = self._attempt_code_glyph_attack(question, ocr_doc)
        if code_glyph_result:
            logger.debug(
                "[REFACTOR][DETECTION] Code Glyph successful for question %s", 
                q_number
            )
            return code_glyph_result
        
        # Step 2: Fallback to Hidden Text detection
        logger.debug(
            "[REFACTOR][DETECTION] Code Glyph failed for question %s, using Hidden Text fallback", 
            q_number
        )
        return self._fallback_to_hidden_text(question)
    
    def _attempt_code_glyph_attack(
        self, 
        question: Dict[str, Any], 
        ocr_doc: Dict[str, Any]
    ) -> Optional[QuestionAttackResult]:
        """
        Attempt Code Glyph attack with multiple entity options and validation.
        
        Args:
            question: Question dictionary
            ocr_doc: OCR document structure
            
        Returns:
            QuestionAttackResult if successful, None if failed
        """
        q_number = question.get("q_number", "unknown")
        
        try:
            # Step 1: Generate top 3 entity options
            entity_options = self._generate_v3_entities(question, ocr_doc)
            if not entity_options:
                logger.warning("[REFACTOR][DETECTION] No entity options generated for question %s", q_number)
                return None
            
            # Step 2: Try each option with validation until one succeeds
            for i, entities_result in enumerate(entity_options):
                logger.debug(
                    "[REFACTOR][DETECTION] Trying option %d/%d for question %s: %s -> %s",
                    i+1, len(entity_options), q_number,
                    entities_result.get("entities", {}).get("input_entity", ""),
                    entities_result.get("entities", {}).get("output_entity", "")
                )
                
                if self.use_validation:
                    validated_result = self._validate_with_llm(question, entities_result)
                    if validated_result:
                        logger.info(
                            "[REFACTOR][DETECTION] Option %d/%d passed validation for question %s",
                            i+1, len(entity_options), q_number
                        )
                        return validated_result
                    else:
                        logger.debug(
                            "[REFACTOR][DETECTION] Option %d/%d failed validation for question %s",
                            i+1, len(entity_options), q_number
                        )
                        continue
                else:
                    # Skip validation if no API key - use first option
                    logger.debug("[REFACTOR][DETECTION] Skipping LLM validation (no API key) for question %s", q_number)
                    return self._create_code_glyph_result(question, entities_result, f"v3_option_{i+1}_unvalidated")
            
            # All options failed validation
            logger.warning(
                "[REFACTOR][DETECTION] All %d entity options failed validation for question %s",
                len(entity_options), q_number
            )
            return None
            
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] Code Glyph attempt failed for question %s: %s",
                q_number, str(e)
            )
            return None
    
    def _generate_v3_entities(
        self, 
        question: Dict[str, Any], 
        ocr_doc: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Generate top 3 V3 Code Glyph entity options for the question.
        """
        q_number = question.get("q_number", "unknown")
        
        try:
            q_type = (question.get("q_type") or "").strip().lower()
            if q_type in {"long_answer", "short_answer", "comprehension_qa", "fill_blank"}:
                # Use long-form V3 generator directly (one best entity)
                from .code_glyph.entity_generation.entity_service import cg_generate_structured_entities_v3
                logger.info("[REFACTOR][DETECTION] Using long-form V3 entity generator for Q%s", q_number)
                single = cg_generate_structured_entities_v3(question)
                return [single] if single else None
            
            # Default path for MCQ/TF: robust options
            logger.info("[REFACTOR][DETECTION] Calling _generate_robust_entity_options for question %s", q_number)
            entity_options = self._generate_robust_entity_options(question, ocr_doc)
            logger.info("[REFACTOR][DETECTION] _generate_robust_entity_options returned %s options for question %s", len(entity_options) if entity_options else 0, q_number)
            logger.debug("[REFACTOR][DETECTION] Entity options detail for Q%s: %s", q_number, entity_options)
            
            if entity_options:
                logger.info(
                    "[REFACTOR][DETECTION] Generated %d entity options for question %s",
                    len(entity_options), q_number
                )
                for i, option in enumerate(entity_options):
                    entities = option.get("entities", {})
                    logger.debug(
                        "[REFACTOR][DETECTION] Option %d for Q%s: '%s' -> '%s' (pos: %s)",
                        i+1, q_number, 
                        entities.get("input_entity", ""), 
                        entities.get("output_entity", ""),
                        option.get("positions", {})
                    )
                return entity_options
            else:
                logger.warning(
                    "[REFACTOR][DETECTION] No entity options generated for question %s, falling back to legacy V3 entity service",
                    q_number
                )
                return self._fallback_to_legacy_v3_entities(question, ocr_doc)
                
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] Entity generation error for question %s: %s",
                q_number, str(e)
            )
            logger.warning(
                "[REFACTOR][DETECTION] Exception in robust entity generation for question %s, falling back to legacy V3 entity service",
                q_number
            )
            return self._fallback_to_legacy_v3_entities(question, ocr_doc)
    
    def _fallback_to_legacy_v3_entities(
        self, 
        question: Dict[str, Any], 
        ocr_doc: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fallback to legacy V3 entity generation system.
        
        Args:
            question: Question dictionary
            ocr_doc: OCR document structure
            
        Returns:
            List with single V3 entity result from legacy system or None if failed
        """
        q_number = question.get("q_number", "unknown")
        
        try:
            # Import legacy V3 entity generation
            from .code_glyph.entity_generation.entity_service import generate_code_glyph_v3_entities
            
            logger.info(
                "[REFACTOR][DETECTION] Using legacy V3 entity generation for question %s",
                q_number
            )
            
            # Call legacy V3 entity generation
            legacy_result = generate_code_glyph_v3_entities(
                questions=[question],
                ocr_doc=ocr_doc
            )
            
            if legacy_result and len(legacy_result) > 0:
                # Convert single legacy result to list format
                single_result = legacy_result[0]
                logger.info(
                    "[REFACTOR][DETECTION] Legacy V3 entity generation successful for question %s: %s -> %s",
                    q_number, 
                    single_result.get("entities", {}).get("input_entity", ""),
                    single_result.get("entities", {}).get("output_entity", "")
                )
                return [single_result]  # Return as list for consistency
            else:
                logger.warning(
                    "[REFACTOR][DETECTION] Legacy V3 entity generation failed for question %s",
                    q_number
                )
                return None
                
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] Legacy V3 entity generation error for question %s: %s",
                q_number, str(e)
            )
            return None
    
    def _validate_with_llm(
        self, 
        question: Dict[str, Any], 
        entities_result: Dict[str, Any]
    ) -> Optional[QuestionAttackResult]:
        """
        Validate Code Glyph entities using LLM verification.
        
        Args:
            question: Question dictionary
            entities_result: V3 entities generation result
            
        Returns:
            QuestionAttackResult if validation passes, None if failed
        """
        q_number = question.get("q_number", "unknown")
        
        try:
            # Import validation service
            from ..evaluation.openai_eval_service import validate_parsed_question_once
            
            # Prepare validation payload
            val_payload = {
                "q_type": question.get("q_type", ""),
                "stem_text": question.get("stem_text", ""),
                "options": question.get("options", {}),
                "correct_answer": question.get("correct_answer") or question.get("gold_answer"),
                "candidate": {
                    "visual_entity": entities_result["entities"]["input_entity"],
                    "parsed_entity": entities_result["entities"]["output_entity"],
                    "positions": entities_result.get("positions", {}),
                    "target_wrong": entities_result.get("target_wrong")
                }
            }
            logger.debug("[REFACTOR][DETECTION] Entities result for Q%s prior to validation: %s", q_number, entities_result)
            
            # Call validation LLM
            logger.debug("[REFACTOR][DETECTION] Validation payload for Q%s: %s", q_number, val_payload)
            verdict = validate_parsed_question_once(val_payload) or {}
            logger.debug("[REFACTOR][DETECTION] Validation raw verdict for Q%s: %s", q_number, verdict)
            flip_ok = bool(verdict.get("flip_result"))
            
            logger.debug(
                "[REFACTOR][DETECTION] Validation result for question %s: flip_ok=%s, verdict=%s",
                q_number, flip_ok, verdict
            )
            
            if flip_ok:
                # Primary candidate validated successfully
                logger.debug(
                    "[REFACTOR][DETECTION] Primary V3 candidate validated for question %s",
                    q_number
                )
                return self._create_code_glyph_result(question, entities_result, "v3_primary")
            
            else:
                # Try alternatives from validation response
                alternatives = verdict.get("alternatives", [])
                logger.debug(
                    "[REFACTOR][DETECTION] Primary candidate failed, trying %d alternatives for question %s",
                    len(alternatives), q_number
                )
                
                for alt in alternatives:
                    if self._validate_alternative(question, alt):
                        # Alternative validated successfully
                        alt_entities_result = self._convert_alternative_to_entities_result(alt, entities_result)
                        logger.debug(
                            "[REFACTOR][DETECTION] Alternative validated for question %s: %s",
                            q_number, alt.get("visual_entity", "")
                        )
                        return self._create_code_glyph_result(question, alt_entities_result, "alternative")
                
                # All validation failed - return None to trigger next entity option
                logger.debug(
                    "[REFACTOR][DETECTION] All validation failed for question %s",
                    q_number
                )
                return None
                
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] LLM validation error for question %s: %s",
                q_number, str(e)
            )
            return None
    
    def _validate_alternative(
        self, 
        question: Dict[str, Any], 
        alternative: Dict[str, Any]
    ) -> bool:
        """
        Validate an alternative candidate using local validation.
        
        Args:
            question: Question dictionary
            alternative: Alternative candidate from LLM
            
        Returns:
            True if alternative is valid locally
        """
        try:
            # Import local validation
            from .code_glyph.entity_generation.entity_service import _validate_candidate_local
            
            stem_text = question.get("stem_text", "")
            visual_entity = str(alternative.get("visual_entity", ""))
            parsed_entity = str(alternative.get("parsed_entity", ""))
            positions = alternative.get("positions", {})
            
            # Run local validation
            _validate_candidate_local(stem_text, visual_entity, parsed_entity, positions)
            
            # Also check that alternative claims to flip successfully
            return bool(alternative.get("flip_result"))
            
        except Exception as e:
            logger.debug(
                "[REFACTOR][DETECTION] Alternative validation failed: %s", 
                str(e)
            )
            return False
    
    def _convert_alternative_to_entities_result(
        self, 
        alternative: Dict[str, Any], 
        original_entities_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert alternative candidate to entities result format.
        
        Args:
            alternative: Alternative candidate from LLM
            original_entities_result: Original V3 entities result for structure
            
        Returns:
            Entities result in V3 format
        """
        # Create new entities result based on alternative
        entities_result = dict(original_entities_result)
        
        # Update core entities
        entities_result["entities"] = {
            "input_entity": str(alternative.get("visual_entity", "")),
            "output_entity": str(alternative.get("parsed_entity", ""))
        }
        
        # Update positions if provided
        if alternative.get("positions"):
            entities_result["positions"] = alternative["positions"]
            
            # Update anchor for backward compatibility
            cs = int(alternative["positions"].get("char_start", 0))
            ce = int(alternative["positions"].get("char_end", 0))
            stem_text = entities_result.get("stem_text", "")
            entities_result["anchor"] = {
                "char_start": cs,
                "char_end": ce,
                "anchor_text": stem_text[cs:ce] if stem_text else ""
            }
        
        # Mark as alternative selection
        entities_result["_chosen_from"] = "alternative"
        
        return entities_result
    
    def _create_code_glyph_result(
        self, 
        question: Dict[str, Any], 
        entities_result: Dict[str, Any],
        selection_method: str
    ) -> QuestionAttackResult:
        """
        Create QuestionAttackResult for successful Code Glyph attack.
        
        Args:
            question: Question dictionary
            entities_result: V3 entities result
            selection_method: Method used to select entities
            
        Returns:
            QuestionAttackResult for Code Glyph
        """
        q_number = question.get("q_number", "unknown")
        entities = entities_result.get("entities", {})
        
        result = QuestionAttackResult(
            question_id=str(q_number),
            attack_method="code_glyph",
            success=True,
            entities=entities,
            wrong_answer=entities_result.get("target_wrong"),
            metadata={
                "selection_method": selection_method,
                "visual_entity": entities.get("input_entity", ""),
                "parsed_entity": entities.get("output_entity", ""),
                "positions": entities_result.get("positions", {}),
                "anchor": entities_result.get("anchor", {}),
                "transformation": entities_result.get("transformation", ""),
                "evidence_tokens": entities_result.get("evidence_tokens", [])
            }
        )
        
        logger.debug(
            "[REFACTOR][DETECTION] Created Code Glyph result for question %s: %s -> %s",
            q_number, entities.get("input_entity", ""), entities.get("output_entity", "")
        )
        
        return result
    
    def _fallback_to_hidden_text(self, question: Dict[str, Any]) -> QuestionAttackResult:
        """
        Fallback to Hidden Text detection for the question.
        
        Args:
            question: Question dictionary
            
        Returns:
            QuestionAttackResult for Hidden Text fallback
        """
        q_number = question.get("q_number", "unknown")
        
        # Generate wrong answer for hidden text detection
        wrong_answer = self._generate_wrong_answer_for_hidden_text(question)
        
        result = QuestionAttackResult(
            question_id=str(q_number),
            attack_method="hidden_text",
            success=True,  # Hidden text fallback always succeeds
            entities=None,  # No entity substitution for hidden text
            wrong_answer=wrong_answer,
            metadata={
                "fallback_reason": "code_glyph_failed",
                "hidden_text_type": "detection",
                "wrong_answer_length": len(wrong_answer) if wrong_answer else 0
            }
        )
        
        logger.debug(
            "[REFACTOR][DETECTION] Created Hidden Text fallback result for question %s",
            q_number
        )
        
        return result
    
    def _generate_wrong_answer_for_hidden_text(self, question: Dict[str, Any]) -> Optional[str]:
        """
        Generate wrong answer for hidden text detection.
        
        Args:
            question: Question dictionary
            
        Returns:
            Wrong answer string or None
        """
        try:
            # Use existing wrong answer generation
            from ..answers.wrong_answer_service import generate_wrong_answer_for_question
            from ..attacks.attack_service import AttackType
            
            # Generate wrong answer using existing service
            wrong_answer_data = generate_wrong_answer_for_question(
                question=question,
                attack_type=AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP,
                ocr_doc=None  # Not needed for hidden text
            )
            
            return wrong_answer_data.get("wrong_answer")
            
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] Failed to generate wrong answer for hidden text: %s",
                str(e)
            )
            # Fallback: use a generic wrong answer
            return "B"  # Simple fallback for MCQ
    
    def _create_fallback_result(self, question: Dict[str, Any], error_msg: str) -> QuestionAttackResult:
        """
        Create fallback result when everything fails.
        
        Args:
            question: Question dictionary
            error_msg: Error message
            
        Returns:
            QuestionAttackResult for error fallback
        """
        q_number = question.get("q_number", "unknown")
        
        result = QuestionAttackResult(
            question_id=str(q_number),
            attack_method="hidden_text",
            success=False,
            entities=None,
            wrong_answer=None,
            metadata={
                "fallback_reason": "processing_error",
                "error_message": error_msg[:200]  # Limit error message length
            }
        )
        
        logger.debug(
            "[REFACTOR][DETECTION] Created error fallback result for question %s",
            q_number
        )
        
        return result
    
    def _generate_robust_entity_options(
        self, 
        question: Dict[str, Any], 
        ocr_doc: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate up to 3 robust entity options using flexible substring approach.
        
        Args:
            question: Question dictionary
            ocr_doc: OCR document structure
            
        Returns:
            List of entity options (up to 3) with different visual entities
        """
        q_number = question.get("q_number", "unknown")
        stem_text = question.get("stem_text", "")
        
        if not stem_text:
            logger.warning("[REFACTOR][DETECTION] No stem text for question %s", q_number)
            return []
        
        logger.debug(
            "[REFACTOR][DETECTION] Generating robust entity options for question %s (stem length: %d)", 
            q_number, len(stem_text)
        )
        
        try:
            # Generate wrong answer options for this question
            wrong_answers = self._generate_target_wrong_answers(question)
            logger.debug("[REFACTOR][DETECTION] Wrong answer candidates for Q%s: %s", q_number, wrong_answers)
            if not wrong_answers:
                logger.warning("[REFACTOR][DETECTION] No target wrong answers for question %s", q_number)
                return []
            
            # Extract candidate substrings from stem text
            candidate_substrings = self._extract_candidate_substrings(stem_text)
            logger.debug("[REFACTOR][DETECTION] Candidate substrings for Q%s: %s", q_number, candidate_substrings[:20])
            if not candidate_substrings:
                logger.warning("[REFACTOR][DETECTION] No candidate substrings for question %s", q_number)
                return []
            
            entity_options = []
            
            # Try to generate options for each target wrong answer
            for target_wrong in wrong_answers[:2]:  # Limit to 2 target wrongs for efficiency
                # Try different candidate substrings for this target
                for visual_entity in candidate_substrings[:10]:  # Limit candidates to avoid timeout
                    if len(entity_options) >= 3:  # Stop once we have 3 options
                        break
                        
                    # Generate parsed entities for this visual entity
                    parsed_options = self._generate_parsed_entity_options(visual_entity, target_wrong)
                    
                    for parsed_entity in parsed_options:
                        if len(entity_options) >= 3:  # Stop once we have 3 options
                            break
                            
                        # Create entity option
                        option = self._create_entity_option(
                            question, visual_entity, parsed_entity, target_wrong, stem_text
                        )
                        
                        if option:
                            entity_options.append(option)
                            logger.debug("[REFACTOR][DETECTION] Option detail for Q%s: %s", q_number, option)
                            logger.debug(
                                "[REFACTOR][DETECTION] Generated option %d for Q%s: '%s' -> '%s' (target: %s)",
                                len(entity_options), q_number, visual_entity, parsed_entity, target_wrong
                            )
                
                if len(entity_options) >= 3:  # Stop once we have 3 options
                    break
            
            logger.info(
                "[REFACTOR][DETECTION] Generated %d robust entity options for question %s",
                len(entity_options), q_number
            )
            
            return entity_options
            
        except Exception as e:
            logger.error(
                "[REFACTOR][DETECTION] Error generating robust entity options for question %s: %s",
                q_number, str(e)
            )
            return []
    
    def _generate_target_wrong_answers(self, question: Dict[str, Any]) -> List[str]:
        """
        Generate target wrong answers for the question.
        
        Args:
            question: Question dictionary
            
        Returns:
            List of target wrong answer strings
        """
        wrong_answers = []
        
        # Get options and exclude correct answer
        correct_answer = question.get("correct_answer") or question.get("gold_answer")
        options = question.get("options", {})
        
        if isinstance(options, dict):
            for key, value in options.items():
                if key != correct_answer:
                    wrong_answers.append(key)
        
        # If no options available, generate generic wrong answers
        if not wrong_answers:
            wrong_answers = ["A", "B", "C", "D"]  # Generic MCQ options
            if correct_answer in wrong_answers:
                wrong_answers.remove(correct_answer)
        
        logger.debug(
            "[REFACTOR][DETECTION] Target wrong answers for Q%s: %s (correct: %s)",
            question.get("q_number", "unknown"), wrong_answers, correct_answer
        )
        
        return wrong_answers
    
    def _extract_candidate_substrings(self, stem_text: str) -> List[str]:
        """
        Extract candidate visual entity substrings using strategic analysis.
        
        This method implements sophisticated entity selection strategies that consider:
        - Question type patterns and optimal substitution points
        - Semantic importance of words and phrases
        - Visual similarity potential for Code Glyph attacks
        - Context-aware substring extraction
        
        Args:
            stem_text: Question stem text
            
        Returns:
            List of strategically selected candidate substring entities
        """
        import re
        
        candidates = []
        words = stem_text.split()
        
        # Strategy 1: Articles and common words (high substitution success)
        # These are often overlooked by readers but critical for meaning
        article_patterns = ['a', 'an', 'the', 'is', 'are', 'was', 'were', 'in', 'on', 'at', 'to', 'of', 'for', 'by', 'from']
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word.lower())
            if clean_word in article_patterns:
                candidates.append(clean_word)
        
        # Strategy 2: Word endings and prefixes that can change meaning
        # Target morphological elements that alter semantic meaning
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word)
            if len(clean_word) >= 4:
                # Common prefixes
                if clean_word[:2] in ['un', 'in', 're', 'de', 'ex']:
                    candidates.append(clean_word[:2])
                # Common suffixes  
                if clean_word[-2:] in ['ed', 'er', 'ly', 'es', 'en']:
                    candidates.append(clean_word[-2:])
                if clean_word[-3:] in ['ing', 'ion', 'est', 'ful']:
                    candidates.append(clean_word[-3:])
        
        # Strategy 3: Short function words and conjunctions
        function_words = ['or', 'and', 'but', 'not', 'no', 'if', 'so', 'as', 'do', 'be', 'we', 'he', 'it']
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word.lower())
            if clean_word in function_words:
                candidates.append(clean_word)
        
        # Strategy 4: Strategic content words (2-6 chars, high impact)
        content_candidates = []
        for word in words:
            clean_word = re.sub(r'[^\w]', '', word)
            if 2 <= len(clean_word) <= 6 and clean_word.isalpha():
                # Prioritize words that could change question meaning significantly
                if any(pattern in clean_word.lower() for pattern in ['tion', 'ness', 'ment', 'able', 'ible']):
                    content_candidates.insert(0, clean_word)  # High priority
                else:
                    content_candidates.append(clean_word)
        
        # Sort content words by strategic value (shorter = higher visual substitution success)
        content_candidates.sort(key=lambda x: (len(x), x.lower()))
        candidates.extend(content_candidates[:8])  # Take top strategic content words
        
        # Strategy 2: Two-word phrases
        for i in range(len(words) - 1):
            phrase = f"{words[i]} {words[i+1]}"
            clean_phrase = re.sub(r'[^\w\s]', '', phrase).strip()
            if 4 <= len(clean_phrase) <= 20:  # Reasonable phrase length
                candidates.append(clean_phrase)
        
        # Strategy 3: Short character substrings (3-6 chars)
        for i in range(len(stem_text)):
            for length in [3, 4, 5, 6]:
                if i + length <= len(stem_text):
                    substring = stem_text[i:i+length]
                    if substring.isalpha() and substring not in candidates:
                        candidates.append(substring)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate.lower() not in seen:
                seen.add(candidate.lower())
                unique_candidates.append(candidate)
        
        logger.debug(
            "[REFACTOR][DETECTION] Extracted %d candidate substrings (showing first 10): %s",
            len(unique_candidates), unique_candidates[:10]
        )
        
        return unique_candidates
    
    def _generate_parsed_entity_options(self, visual_entity: str, target_wrong: str) -> List[str]:
        """
        Generate parsed entity options that are <= size of visual entity.
        
        For long-form q_types, ignore target_wrong and return impactful flips
        using curated opposites (e.g., must→may, all→any, include→exclude, before→after,
        maximum→minimum, at least→at most, exactly→at most) and small numeric shifts,
        always enforcing len(parsed) <= len(visual).
        """
        parsed_options: List[str] = []
        max_length = len(visual_entity)
        visual_lower = (visual_entity or "").lower().strip()
        if max_length <= 0:
            return []
        
        # Curated impactful flips
        flip_map = {
            "must": "may",
            "shall": "may",
            "require": "allow",
            "requires": "allows",
            "required": "optional",
            "all": "any",
            "every": "some",
            "include": "exclude",
            "includes": "excludes",
            "before": "after",
            "after": "before",
            "maximum": "minimum",
            "minimum": "maximum",
            "at least": "at most",
            "at most": "at least",
            "exactly": "at most",
            "distinct": "any",
            "and": "or",
            "or": "and",
            "prove": "disprove",
        }
        for k, v in flip_map.items():
            if k in visual_lower and len(v) <= max_length:
                parsed_options.append(v)
        
        # Numeric contractions (prefer smaller numbers)
        try:
            if visual_lower.isdigit():
                n = int(visual_lower)
                for m in [n - 2, n - 1, max(1, n // 2)]:
                    s = str(m)
                    if len(s) <= max_length and s != visual_entity:
                        parsed_options.append(s)
        except Exception:
            pass
        
        # Fallback tiny negations/opposites for short tokens
        tiny_map = {
            "yes": "no",
            "true": "false",
            "correct": "wrong",
            "high": "low",
            "more": "less",
            "up": "down",
            "in": "out",
        }
        for k, v in tiny_map.items():
            if k == visual_lower and len(v) <= max_length:
                parsed_options.append(v)
        
        # De-duplicate preserve order
        unique_parsed: List[str] = []
        for option in parsed_options:
            if option not in unique_parsed:
                unique_parsed.append(option)
        
        logger.debug(
            "[REFACTOR][DETECTION] Generated %d parsed options for visual '%s': %s",
            len(unique_parsed), visual_entity, unique_parsed[:5]
        )
        return unique_parsed
    
    def _create_entity_option(
        self, 
        question: Dict[str, Any], 
        visual_entity: str, 
        parsed_entity: str, 
        target_wrong: str,
        stem_text: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a complete entity option with positions and validation.
        
        Args:
            question: Question dictionary
            visual_entity: Visual entity text
            parsed_entity: Parsed entity text
            target_wrong: Target wrong answer
            stem_text: Question stem text
            
        Returns:
            Complete entity option dictionary or None if invalid
        """
        try:
            # Find positions of visual entity in stem text
            start_pos = stem_text.find(visual_entity)
            if start_pos == -1:
                # Try case-insensitive search
                start_pos = stem_text.lower().find(visual_entity.lower())
                if start_pos == -1:
                    logger.debug(
                        "[REFACTOR][DETECTION] Visual entity '%s' not found in stem text",
                        visual_entity
                    )
                    return None
            
            end_pos = start_pos + len(visual_entity)
            
            # Create positions structure
            positions = {
                "char_start": start_pos,
                "char_end": end_pos,
                "length": len(visual_entity)
            }
            
            # Create anchor structure for backward compatibility
            anchor = {
                "char_start": start_pos,
                "char_end": end_pos,
                "anchor_text": visual_entity
            }
            
            # Basic validation: parsed entity should be <= visual entity size
            if len(parsed_entity) > len(visual_entity):
                logger.debug(
                    "[REFACTOR][DETECTION] Parsed entity '%s' longer than visual entity '%s'",
                    parsed_entity, visual_entity
                )
                return None
            
            # Create entity option
            option = {
                "entities": {
                    "input_entity": visual_entity,
                    "output_entity": parsed_entity
                },
                "positions": positions,
                "anchor": anchor,
                "target_wrong": target_wrong,
                "stem_text": stem_text,
                "transformation": f"'{visual_entity}' -> '{parsed_entity}'",
                "evidence_tokens": [visual_entity],
                "_generation_method": "robust_substring"
            }
            
            return option
            
        except Exception as e:
            logger.debug(
                "[REFACTOR][DETECTION] Error creating entity option for '%s' -> '%s': %s",
                visual_entity, parsed_entity, str(e)
            )
            return None