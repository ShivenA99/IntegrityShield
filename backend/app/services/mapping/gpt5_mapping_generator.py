"""GPT-5 powered mapping generator service."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from ...extensions import db
from ...models import QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.integration.external_api_client import ExternalAIClient
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now

from .gpt5_config import (
    GPT5_MODEL,
    GPT5_MAX_TOKENS,
    GPT5_TEMPERATURE,
    MAPPINGS_PER_QUESTION,
    MAX_RETRIES,
    RETRY_DELAY,
)
from .mapping_generation_logger import get_mapping_logger
from .mapping_strategies import get_strategy_registry
from .mapping_validator import MappingValidator


class GPT5MappingGeneratorService:
    """Service for generating mappings using GPT-5."""
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.structured_manager = StructuredDataManager()
        self.ai_client = ExternalAIClient()
        self.validator = MappingValidator()
        self.strategy_registry = get_strategy_registry()
        self.mapping_logger = get_mapping_logger()
    
    def generate_mappings_for_question(
        self,
        run_id: str,
        question_id: int,
        k: int = MAPPINGS_PER_QUESTION,
        strategy_name: str = "replacement"
    ) -> Dict[str, Any]:
        """
        Generate k mappings for a single question.
        
        Returns:
            Dictionary with generation results and validated mapping
        """
        # Load question data
        question = QuestionManipulation.query.filter_by(
            pipeline_run_id=run_id,
            id=question_id
        ).first()
        
        if not question:
            raise ValueError(f"Question {question_id} not found for run {run_id}")
        
        # Load structured data
        structured = self.structured_manager.load(run_id)
        
        # Get question data
        question_data = self._get_question_data(run_id, question, structured)
        
        # Normalize question_data to ensure all dictionary keys are strings
        question_data = self._normalize_dict_keys(question_data)
        
        # Get LaTeX stem text
        latex_stem_text = self._extract_latex_stem_text(run_id, question, structured)
        if not latex_stem_text:
            raise ValueError(f"Could not extract LaTeX stem text for question {question_id}")
        
        question_data["latex_stem_text"] = latex_stem_text
        
        # Get strategy
        strategy = self.strategy_registry.get_strategy(
            question_data.get("question_type", "mcq_single"),
            strategy_name
        )
        if not strategy:
            raise ValueError(
                f"No strategy found for question type {question_data.get('question_type')} "
                f"with strategy {strategy_name}"
            )
        
        # Generate mappings
        try:
            mappings = self._call_gpt5_for_mapping(
                question_data=question_data,
                strategy=strategy,
                k=k,
                run_id=run_id
            )
            
            self.mapping_logger.log_generation(
                run_id=run_id,
                question_id=question_id,
                question_number=question.question_number,
                status="success",
                details={
                    "mappings_generated": len(mappings),
                    "strategy": strategy_name,
                    "prompt_used": self.strategy_registry.build_prompt(strategy, question_data, k)
                },
                mappings_generated=len(mappings)
            )
            
            # Validate mappings
            # Use stem_text (plain text) for validation, not latex_stem_text
            # The validation applies mappings to plain text, not LaTeX
            first_valid_mapping, validation_logs = self.validator.validate_mapping_sequence(
                question_text=question_data.get("stem_text", ""),
                question_type=question_data.get("question_type", ""),
                gold_answer=question_data.get("gold_answer", ""),
                options_data=question_data.get("options", {}),
                mappings=mappings,
                run_id=run_id
            )
            
            # Log validations
            for idx, validation_log in enumerate(validation_logs):
                self.mapping_logger.log_validation(
                    run_id=run_id,
                    question_id=question_id,
                    question_number=question.question_number,
                    mapping_index=validation_log.get("mapping_index", idx),
                    status=validation_log.get("status", "unknown"),
                    details=validation_log
                )
            
            # Save first valid mapping if found
            if first_valid_mapping:
                self._save_mapping_to_question(question, first_valid_mapping)
                # Sync to structured.json
                self._sync_mapping_to_structured(run_id, question, first_valid_mapping)
                return {
                    "status": "success",
                    "mappings_generated": len(mappings),
                    "mappings_validated": len(validation_logs),
                    "first_valid_mapping_index": validation_logs.index(
                        next(log for log in validation_logs if log.get("status") == "success")
                    ) if any(log.get("status") == "success" for log in validation_logs) else None,
                    "mapping": first_valid_mapping,
                    "validation_logs": validation_logs
                }
            else:
                return {
                    "status": "no_valid_mapping",
                    "mappings_generated": len(mappings),
                    "mappings_validated": len(validation_logs),
                    "first_valid_mapping_index": None,
                    "mapping": None,
                    "validation_logs": validation_logs
                }
        
        except Exception as e:
            self.logger.error(f"Failed to generate mappings for question {question_id}: {e}", run_id=run_id)
            self.mapping_logger.log_generation(
                run_id=run_id,
                question_id=question_id,
                question_number=question.question_number,
                status="failed",
                details={"error": str(e)},
                mappings_generated=0
            )
            raise
    
    def generate_mappings_for_all_questions(
        self,
        run_id: str,
        k: int = MAPPINGS_PER_QUESTION,
        strategy_name: str = "replacement"
    ) -> Dict[str, Any]:
        """
        Generate mappings for all questions asynchronously.
        
        Returns:
            Dictionary with generation status for all questions
        """
        questions = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()
        
        results = {}
        for question in questions:
            try:
                result = self.generate_mappings_for_question(
                    run_id=run_id,
                    question_id=question.id,
                    k=k,
                    strategy_name=strategy_name
                )
                # Convert question.id to string for JSON serialization
                results[str(question.id)] = result
            except Exception as e:
                self.logger.error(
                    f"Failed to generate mappings for question {question.id}: {e}",
                    run_id=run_id
                )
                # Convert question.id to string for JSON serialization
                results[str(question.id)] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return {
            "run_id": run_id,
            "total_questions": len(questions),
            "results": results
        }
    
    def _call_gpt5_for_mapping(
        self,
        question_data: Dict[str, Any],
        strategy: Any,
        k: int,
        run_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Call GPT-5 API to generate mappings."""
        # Normalize question_data to ensure all dictionary keys are strings
        question_data = self._normalize_dict_keys(question_data)
        
        # Build prompt with error handling
        try:
            prompt = self.strategy_registry.build_prompt(strategy, question_data, k)
        except Exception as e:
            self.logger.error(
                f"Failed to build prompt: {e}",
                run_id=run_id,
                question_number=question_data.get("question_number"),
                exc_info=True
            )
            raise ValueError(f"Failed to build prompt: {e}") from e
        
        # Prepare messages
        messages = [
            {
                "role": "system",
                "content": "You are an expert at generating text substitutions for academic questions. Return only valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        # Call GPT-5 API
        for attempt in range(MAX_RETRIES):
            try:
                # Use OpenAI client directly for GPT-5
                import os
                from openai import OpenAI
                
                api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not configured")
                
                client = OpenAI(api_key=api_key)
                
                # Prepare request
                request_args: Dict[str, Any] = {
                    "model": GPT5_MODEL,
                    "messages": messages,
                    "temperature": GPT5_TEMPERATURE,
                    "max_tokens": GPT5_MAX_TOKENS
                }
                
                # Add response format for JSON if supported
                if GPT5_MODEL.lower().startswith("gpt-4o"):
                    request_args["response_format"] = {"type": "json_object"}
                
                # Make API call
                response_obj = client.chat.completions.create(**request_args)
                
                # Extract response
                content = response_obj.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from GPT-5 API")
                
                response = {
                    "response": content,
                    "raw_response": response_obj
                }
                
                # Parse response
                mappings = self._parse_mapping_response(response, question_data)
                
                # Add latex_stem_text to each mapping if not present
                for mapping in mappings:
                    if "latex_stem_text" not in mapping:
                        mapping["latex_stem_text"] = question_data.get("latex_stem_text", "")
                    if "question_index" not in mapping:
                        mapping["question_index"] = question_data.get("question_number", "")
                
                # Validate mappings
                validated_mappings = []
                for mapping in mappings:
                    if self._validate_mapping_structure(mapping, question_data):
                        validated_mappings.append(mapping)
                
                if validated_mappings:
                    return validated_mappings[:k]
                else:
                    self.logger.warning(
                        f"No valid mappings found in response (attempt {attempt + 1}/{MAX_RETRIES})",
                        run_id=run_id
                    )
            
            except Exception as e:
                self.logger.warning(
                    f"GPT-5 API call failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}",
                    run_id=run_id
                )
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    raise
        
        raise RuntimeError(f"Failed to generate mappings after {MAX_RETRIES} attempts")
    
    def _parse_mapping_response(
        self,
        response: Dict[str, Any],
        question_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Parse GPT-5 response to extract mappings."""
        content = response.get("response", "")
        if not content:
            raise ValueError("Empty response from GPT-5")
        
        # Try to parse as JSON
        try:
            # Remove markdown formatting if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            # Parse JSON
            data = json.loads(content.strip())
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                if "mappings" in data:
                    return data["mappings"]
                elif "questions" in data:
                    return data["questions"]
                else:
                    # Assume single mapping
                    return [data]
            else:
                raise ValueError(f"Unexpected response format: {type(data)}")
        
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON response: {e}")
            self.logger.debug(f"Response content: {content[:500]}")
            raise ValueError(f"Invalid JSON response: {e}")
    
    def _validate_mapping_structure(
        self,
        mapping: Dict[str, Any],
        question_data: Dict[str, Any]
    ) -> bool:
        """Validate that mapping has required structure."""
        required_fields = [
            "question_index",
            "latex_stem_text",
            "original_substring",
            "replacement_substring",
            "start_pos",
            "end_pos"
        ]
        
        for field in required_fields:
            if field not in mapping:
                self.logger.warning(f"Mapping missing required field: {field}")
                return False
        
        # Validate positions
        start_pos = mapping.get("start_pos", -1)
        end_pos = mapping.get("end_pos", -1)
        original = mapping.get("original_substring", "")
        latex_stem = mapping.get("latex_stem_text", "")
        
        if start_pos < 0 or end_pos <= start_pos:
            self.logger.warning(f"Invalid positions: start={start_pos}, end={end_pos}")
            return False
        
        if end_pos > len(latex_stem):
            self.logger.warning(f"End position {end_pos} exceeds latex_stem_text length {len(latex_stem)}")
            return False
        
        # Verify original substring matches
        actual_substring = latex_stem[start_pos:end_pos]
        if actual_substring != original:
            self.logger.warning(
                f"Original substring mismatch: expected '{original}', got '{actual_substring}' "
                f"at position {start_pos}-{end_pos}"
            )
            return False
        
        return True
    
    def _normalize_dict_keys(self, obj: Any) -> Any:
        """Recursively normalize dictionary keys to strings.
        
        This ensures all dictionary keys are strings, preventing "Dict key must be str" errors.
        """
        if isinstance(obj, dict):
            normalized = {}
            for key, value in obj.items():
                # Convert key to string
                key_str = str(key) if not isinstance(key, str) else key
                # Recursively normalize nested dictionaries
                normalized[key_str] = self._normalize_dict_keys(value)
            return normalized
        elif isinstance(obj, list):
            # Recursively normalize list items
            return [self._normalize_dict_keys(item) for item in obj]
        else:
            # Return primitive types as-is
            return obj
    
    def _get_question_data(
        self,
        run_id: str,
        question: QuestionManipulation,
        structured: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get question data for mapping generation."""
        # Get AI question data if available
        ai_questions = structured.get("ai_questions", [])
        ai_question = None
        for aq in ai_questions:
            if str(aq.get("question_number", "")) == str(question.question_number):
                ai_question = aq
                break
        
        # Get options and normalize keys
        options = (
            ai_question.get("options") if ai_question
            else question.options_data or {}
        )
        options = self._normalize_dict_keys(options) if options else {}
        
        # Get metadata and normalize keys
        metadata = ai_question.get("metadata", {}) if ai_question else {}
        metadata = self._normalize_dict_keys(metadata) if metadata else {}
        
        # Build question data
        question_data = {
            "question_number": question.question_number,
            "question_type": question.question_type or "mcq_single",
            "stem_text": (
                ai_question.get("stem_text") if ai_question
                else question.original_text
            ),
            "gold_answer": question.gold_answer or "",
            "options": options,
            "metadata": metadata
        }
        
        return question_data
    
    def _extract_latex_stem_text(
        self,
        run_id: str,
        question: QuestionManipulation,
        structured: Dict[str, Any]
    ) -> Optional[str]:
        """Extract LaTeX stem text for a question."""
        # Get LaTeX file path
        document_meta = structured.get("document", {})
        latex_path = document_meta.get("latex_path")
        
        if not latex_path:
            self.logger.warning(f"No LaTeX path found for run {run_id}")
            return None
        
        latex_file = Path(latex_path)
        if not latex_file.exists():
            self.logger.warning(f"LaTeX file not found: {latex_path}")
            return None
        
        # Read LaTeX content
        try:
            latex_content = latex_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            latex_content = latex_file.read_text(encoding="latin-1")
        
        # Find question segment
        question_segment = self._find_question_segment_in_latex(
            latex_content,
            question.question_number
        )
        
        if not question_segment:
            self.logger.warning(
                f"Could not find question segment for question {question.question_number} in LaTeX"
            )
            return None
        
        # Extract stem text from segment (raw LaTeX for exact matching)
        segment_text = latex_content[question_segment[0]:question_segment[1]]
        # Return raw LaTeX text for exact matching
        # GPT-5 will generate mappings with positions relative to this exact text
        return segment_text.strip()
    
    def _find_question_segment_in_latex(
        self,
        latex_content: str,
        question_number: str
    ) -> Optional[Tuple[int, int]]:
        """Find question segment in LaTeX content."""
        # Try to find question using \item pattern
        # Look for \item followed by question number
        pattern = re.compile(
            rf"\\item\s+{re.escape(question_number)}\.",
            re.IGNORECASE
        )
        
        match = pattern.search(latex_content)
        if not match:
            # Try without period
            pattern = re.compile(
                rf"\\item\s+{re.escape(question_number)}\s",
                re.IGNORECASE
            )
            match = pattern.search(latex_content)
        
        if not match:
            return None
        
        # Find start of question (after \item)
        start_pos = match.end()
        
        # Find end of question (next \item or \end{enumerate})
        end_pattern = re.compile(r"\\item|\\end\{enumerate\}")
        end_match = end_pattern.search(latex_content, start_pos)
        
        if end_match:
            end_pos = end_match.start()
        else:
            # Use end of document
            end_pos = len(latex_content)
        
        return (start_pos, end_pos)
    
    def _extract_stem_from_segment(self, segment_text: str) -> str:
        """Extract stem text from LaTeX segment."""
        # Remove LaTeX commands but keep text content
        # This is a simplified extraction - in production, you might want more sophisticated parsing
        stem = segment_text
        
        # Remove common LaTeX commands
        stem = re.sub(r"\\textbf\{([^}]*)\}", r"\1", stem)
        stem = re.sub(r"\\textit\{([^}]*)\}", r"\1", stem)
        stem = re.sub(r"\\emph\{([^}]*)\}", r"\1", stem)
        stem = re.sub(r"\\text\{([^}]*)\}", r"\1", stem)
        
        # Remove enumerate environments (options)
        stem = re.sub(r"\\begin\{enumerate\}.*?\\end\{enumerate\}", "", stem, flags=re.DOTALL)
        
        # Clean up whitespace
        stem = re.sub(r"\s+", " ", stem)
        stem = stem.strip()
        
        return stem
    
    def _save_mapping_to_question(
        self,
        question: QuestionManipulation,
        mapping: Dict[str, Any]
    ):
        """Save mapping to question in database."""
        # Convert mapping to substring_mapping format
        substring_mapping = {
            "id": str(uuid.uuid4()),
            "original": mapping.get("original_substring", ""),
            "replacement": mapping.get("replacement_substring", ""),
            "start_pos": mapping.get("start_pos", 0),
            "end_pos": mapping.get("end_pos", 0),
            "context": "question_stem",
            "target_wrong_answer": mapping.get("target_wrong_answer"),
            "reasoning": mapping.get("reasoning", ""),
            # Add positional information for LaTeX matching
            "latex_stem_text": mapping.get("latex_stem_text", ""),
            "question_index": mapping.get("question_index", question.question_number)
        }
        
        # Update question
        question.substring_mappings = [substring_mapping]
        question.manipulation_method = "gpt5_generated"
        
        db.session.add(question)
        db.session.commit()
        
        self.logger.info(
            f"Saved mapping to question {question.question_number}",
            run_id=question.pipeline_run_id
        )
    
    def _sync_mapping_to_structured(
        self,
        run_id: str,
        question: QuestionManipulation,
        mapping: Dict[str, Any]
    ):
        """Sync mapping to structured.json."""
        try:
            from ...services.pipeline.smart_substitution_service import SmartSubstitutionService
            service = SmartSubstitutionService()
            service.sync_structured_mappings(run_id)
            self.logger.info(
                f"Synced mapping to structured.json for question {question.question_number}",
                run_id=run_id
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to sync mapping to structured.json: {e}",
                run_id=run_id
            )

