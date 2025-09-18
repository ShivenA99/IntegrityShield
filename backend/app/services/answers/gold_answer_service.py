"""
Gold Answer Service

Centralized service for generating gold (correct) answers for questions.
Used by both Prevention and Detection attack modes.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class GoldAnswerService:
    """
    Service for generating correct answers to questions using OpenAI.
    
    This service:
    1. Processes questions to generate gold answers
    2. Handles different question types (MCQ, True/False, etc.)
    3. Integrates with existing OpenAI evaluation infrastructure
    4. Provides consistent answer format across attack modes
    """
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        if not self.openai_api_key:
            logger.warning("[REFACTOR][GOLD_ANSWER] No OpenAI API key found - gold answer generation will be skipped")
        
        logger.info("[REFACTOR][GOLD_ANSWER] Initialized gold answer service with model: %s", self.openai_model)
    
    def generate_gold_answers(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Generate gold answers for all questions.
        
        Args:
            questions: List of question dictionaries from OCR
            
        Returns:
            List of questions enhanced with gold answers
        """
        if not self.openai_api_key:
            logger.warning("[REFACTOR][GOLD_ANSWER] Skipping gold answer generation - no API key")
            return questions
        
        logger.info("[REFACTOR][GOLD_ANSWER] Generating gold answers for %d questions", len(questions))
        
        enhanced_questions = []
        for i, question in enumerate(questions):
            try:
                enhanced_question = self._generate_single_gold_answer(question)
                enhanced_questions.append(enhanced_question)
                
                logger.debug(
                    "[REFACTOR][GOLD_ANSWER] Generated gold answer for question %d: %s",
                    i + 1, enhanced_question.get("gold_answer", "N/A")
                )
                
            except Exception as e:
                logger.error(
                    "[REFACTOR][GOLD_ANSWER] Failed to generate gold answer for question %d: %s",
                    i + 1, str(e)
                )
                # Add original question without gold answer
                enhanced_questions.append(question)
        
        logger.info("[REFACTOR][GOLD_ANSWER] Gold answer generation completed")
        return enhanced_questions
    
    def _generate_single_gold_answer(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate gold answer for a single question.
        
        Args:
            question: Question dictionary
            
        Returns:
            Question dictionary enhanced with gold_answer field
        """
        q_type = question.get("q_type", "").lower()
        stem_text = question.get("stem_text", "")
        options = question.get("options", {})
        
        # Skip if question already has a gold answer
        if question.get("gold_answer"):
            logger.debug("[REFACTOR][GOLD_ANSWER] Question already has gold answer, skipping")
            return question
        
        logger.debug("[REFACTOR][GOLD_ANSWER] Generating gold answer for question type: %s", q_type)
        
        # Use existing OpenAI evaluation infrastructure
        try:
            # Import here to avoid circular dependencies
            from ..evaluation.openai_eval_service import call_openai_eval
            
            # Create evaluation prompt for gold answer generation
            prompt = self._create_gold_answer_prompt(q_type, stem_text, options)
            logger.info("[REFACTOR][GOLD_ANSWER] Gold prompt (first 400 chars): %s", prompt[:400])
            
            # Call OpenAI
            eval_result = call_openai_eval(prompt)
            answer_text = eval_result.get("answer_text", "") if eval_result else ""
            logger.info("[REFACTOR][GOLD_ANSWER] Gold answer_text (first 400 chars): %s", (answer_text or "")[:400])
            
            # Parse answer based on question type
            gold_answer = self._parse_gold_answer(answer_text, q_type, options)
            
            # Return enhanced question
            enhanced_question = dict(question)
            enhanced_question["gold_answer"] = gold_answer
            enhanced_question["gold_generation_method"] = "openai_eval"
            
            return enhanced_question
            
        except Exception as e:
            logger.error("[REFACTOR][GOLD_ANSWER] OpenAI call failed: %s", str(e))
            # Return original question
            return question
    
    def _create_gold_answer_prompt(self, q_type: str, stem_text: str, options: Dict[str, str]) -> str:
        """Create OpenAI prompt for gold answer generation."""
        
        base_prompt = f"Answer this question correctly and concisely:\n\nQuestion: {stem_text}\n"
        
        if q_type in ["mcq_single", "mcq_multi", "true_false"] and options:
            options_text = "\n".join([f"{label}: {text}" for label, text in options.items()])
            base_prompt += f"\nOptions:\n{options_text}\n"
            
            if q_type == "mcq_single":
                base_prompt += "\nProvide only the single correct option label (e.g., 'A')."
            elif q_type == "mcq_multi":
                base_prompt += "\nProvide all correct option labels, comma-separated (e.g., 'A, C')."
            elif q_type == "true_false":
                base_prompt += "\nRespond with exactly 'True' or 'False'."
        else:
            base_prompt += "\nProvide a clear, accurate answer."
        
        return base_prompt
    
    def _parse_gold_answer(self, answer_text: str, q_type: str, options: Dict[str, str]) -> str:
        """Parse OpenAI response into standardized gold answer format."""
        
        if not answer_text:
            return ""
        
        answer_text = answer_text.strip()
        
        # For MCQ and True/False, try to extract option labels
        if q_type in ["mcq_single", "true_false"] and options:
            # Look for exact option labels in response
            for label in options.keys():
                if label.upper() in answer_text.upper():
                    return label
        
        elif q_type == "mcq_multi" and options:
            # Look for multiple option labels
            found_labels = []
            for label in options.keys():
                if label.upper() in answer_text.upper():
                    found_labels.append(label)
            if found_labels:
                return ", ".join(sorted(found_labels))
        
        # For other question types or if no option labels found, return cleaned text
        return answer_text[:200]  # Limit length for database storage