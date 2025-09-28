from __future__ import annotations

import asyncio
from typing import Any, Dict, List
import json
import uuid

from ...extensions import db
from ...models import CharacterMapping, QuestionManipulation
from ...services.data_management.structured_data_manager import StructuredDataManager
from ...services.manipulation.context_aware_processor import ContextAwareProcessor
from ...services.manipulation.substring_manipulator import SubstringManipulator
from ...services.manipulation.universal_character_mapper import MappingResult, UniversalCharacterMapper
from ...services.manipulation.visual_fidelity_validator import VisualFidelityValidator
from ...services.manipulation.effectiveness import aggregate_effectiveness
from ...services.integration.external_api_client import ExternalAIClient
from ...utils.logging import get_logger
from ...utils.time import isoformat, utc_now


class SmartSubstitutionService:
	def __init__(self) -> None:
		self.logger = get_logger(__name__)
		self.structured_manager = StructuredDataManager()
		self.mapper = UniversalCharacterMapper()
		self.substrings = SubstringManipulator()
		self.validator = VisualFidelityValidator()
		self.context_processor = ContextAwareProcessor()
		self.ai_client = ExternalAIClient()

	async def run(self, run_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
		strategy = config.get("mapping_strategy", "unicode_steganography")
		return await asyncio.to_thread(self._apply_mappings, run_id, strategy)

	def _apply_mappings(self, run_id: str, strategy: str) -> Dict[str, Any]:
		structured = self.structured_manager.load(run_id)
		questions_data = structured.setdefault("questions", [])
		questions_models = QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all()

		# Ensure we have a stable mapping between DB records and structured entries
		structured_by_qnum = {}
		for entry in questions_data:
			label = str(entry.get("q_number") or entry.get("question_number") or "").strip()
			if label:
				structured_by_qnum[label] = entry

		def ensure_structured_entry(model: QuestionManipulation) -> Dict[str, Any]:
			label = str(model.question_number).strip()
			if label in structured_by_qnum:
				return structured_by_qnum[label]
			node: Dict[str, Any] = {
				"q_number": label,
				"question_number": label,
			}
			questions_data.append(node)
			structured_by_qnum[label] = node
			return node

		# Character map is still produced, but we no longer auto-generate word-level mappings here
		mapping_result = self.mapper.create_mapping(strategy)

		total_effectiveness = 0.0
		mappings_created = 0

		# Compute true gold answers per question up-front
		for question_model in questions_models:
			question_dict = ensure_structured_entry(question_model)
			gold_answer, gold_conf = self._compute_true_gold(question_model)
			question_model.gold_answer = gold_answer
			question_model.gold_confidence = gold_conf
			question_dict["gold_answer"] = gold_answer
			question_dict["gold_confidence"] = gold_conf
			db.session.add(question_model)

		db.session.commit()

		# Initialize manipulation metadata but do not prefill substring_mappings; UI will drive them
		for question_model in questions_models:
			question_dict = ensure_structured_entry(question_model)
			question_model.manipulation_method = question_model.manipulation_method or "smart_substitution"
			self._merge_question_payload(question_dict, question_model)
			# Leave substring_mappings as None if not set; avoid direct assignment which causes MutableList coercion issues
			# The UI will initialize and manage the mappings through the API endpoints
			question_dict["manipulation"] = {
				"method": question_model.manipulation_method,
				"substring_mappings": list(question_model.substring_mappings or []),
				"effectiveness_score": question_model.effectiveness_score,
				"character_strategy": mapping_result.strategy,
			}
			db.session.add(question_model)

		db.session.commit()

		structured["global_mappings"] = {
			"character_strategy": mapping_result.strategy,
			"mapping_dictionary": mapping_result.character_map,
			"effectiveness_stats": {
				"total_questions": len(questions_models),
				"average_effectiveness": (total_effectiveness / len(questions_models)) if questions_models else 0,
				"total_characters_mapped": len(mapping_result.character_map),
				"coverage_percentage": round(mapping_result.coverage * 100, 2),
			},
		}

		metadata = structured.setdefault("pipeline_metadata", {})
		stages_completed = set(metadata.get("stages_completed", []))
		stages_completed.add("smart_substitution")
		metadata.update(
			{
				"current_stage": "smart_substitution",
				"stages_completed": list(stages_completed),
				"last_updated": isoformat(utc_now()),
			}
		)
		self.structured_manager.save(run_id, structured)

		# Persist a CharacterMapping record for reference
		mapping_record = CharacterMapping(
			pipeline_run_id=run_id,
			mapping_strategy=mapping_result.strategy,
			character_map=mapping_result.character_map,
		)
		db.session.add(mapping_record)
		db.session.commit()

		return {
			"questions_processed": len(questions_models),
			"total_substitutions": mappings_created,
			"average_effectiveness": (total_effectiveness / len(questions_models)) if questions_models else 0,
		}

	def _generate_question_mappings(self, question: Dict[str, Any], mapping_result: MappingResult) -> List[Dict]:
		# Deprecated: UI-driven mappings now. Keep method for potential future automation.
		return []

	def _merge_question_payload(self, question_dict: Dict[str, Any], question_model: QuestionManipulation) -> None:
		"""Ensure structured question entry mirrors the database payload for deterministic renders."""
		number = str(question_model.question_number).strip()
		if number:
			question_dict.setdefault("q_number", number)
			question_dict.setdefault("question_number", number)

		if question_model.question_type:
			question_dict["question_type"] = question_model.question_type

		if question_model.original_text:
			question_dict["original_text"] = question_model.original_text

		stem_text = question_dict.get("stem_text") or question_model.original_text
		if stem_text:
			question_dict["stem_text"] = stem_text

		if question_model.options_data:
			question_dict["options"] = question_model.options_data

		if question_model.stem_position:
			question_dict["stem_position"] = question_model.stem_position
			positioning = dict(question_dict.get("positioning") or {})
			page = positioning.get("page") or question_model.stem_position.get("page")
			bbox = positioning.get("bbox") or question_model.stem_position.get("bbox")
			if page is not None:
				positioning["page"] = page
			if bbox is not None:
				positioning["bbox"] = bbox
			if positioning:
				question_dict["positioning"] = positioning

		# Preserve substring mappings and metadata if already provided
		manipulation = dict(question_dict.get("manipulation") or {})
		if question_model.substring_mappings is not None and not manipulation.get("substring_mappings"):
			manipulation["substring_mappings"] = list(question_model.substring_mappings or [])
		if question_model.effectiveness_score is not None:
			manipulation.setdefault("effectiveness_score", question_model.effectiveness_score)
		if manipulation:
			question_dict["manipulation"] = manipulation

	def refresh_question_mapping(self, run_id: str, question_number: str) -> Dict[str, Any]:
		structured = self.structured_manager.load(run_id)
		strategy = structured.get("global_mappings", {}).get("character_strategy", "unicode_steganography")
		mapping_result = self.mapper.create_mapping(strategy)

		questions = structured.get("questions", [])
		question_dict = next((q for q in questions if q.get("q_number") == question_number), None)
		if not question_dict:
			raise ValueError("Question not found in structured data")

		question_model = (
			QuestionManipulation.query.filter_by(pipeline_run_id=run_id, question_number=question_number).first()
		)
		if not question_model:
			raise ValueError("Question manipulation entry missing")

		# Ensure list exists and is JSON-safe - use mutation-only approach
		current_list: List[Dict[str, Any]] = list(question_model.substring_mappings or [])
		json_safe = json.loads(json.dumps(current_list))
		# Only mutate existing MutableList, never assign new list directly
		if question_model.substring_mappings is not None:
			question_model.substring_mappings.clear()
			question_model.substring_mappings.extend(json_safe)
		question_model.effectiveness_score = aggregate_effectiveness(json_safe)
		db.session.add(question_model)
		db.session.commit()

		self._merge_question_payload(question_dict, question_model)
		question_dict["manipulation"] = question_dict.get("manipulation", {})
		question_dict["manipulation"].update(
			{
				"substring_mappings": json_safe,
				"effectiveness_score": question_model.effectiveness_score,
				"method": question_model.manipulation_method or "smart_substitution",
				"character_strategy": mapping_result.strategy,
			}
		)
		self.structured_manager.save(run_id, structured)
		return {
			"substring_mappings": json_safe,
			"effectiveness_score": question_model.effectiveness_score,
		}

	def sync_structured_mappings(self, run_id: str) -> None:
		"""Ensure structured data reflects the latest substring mappings from the database."""
		structured = self.structured_manager.load(run_id)
		if not structured:
			return

		questions = structured.setdefault("questions", [])
		if not questions:
			return

		question_map = {
			str(entry.get("q_number") or entry.get("question_number")): entry for entry in questions
		}
		if not question_map:
			return

		strategy = structured.get("global_mappings", {}).get("character_strategy", "unicode_steganography")

		changed = False
		for model in QuestionManipulation.query.filter_by(pipeline_run_id=run_id).all():
			q_label = str(model.question_number or model.id)
			entry = question_map.get(q_label)
			if not entry:
				entry = {"q_number": q_label, "question_number": q_label}
				questions.append(entry)
				question_map[q_label] = entry
				changed = True

			self._merge_question_payload(entry, model)

			current_list: List[Dict[str, Any]] = list(model.substring_mappings or [])
			json_safe = json.loads(json.dumps(current_list))
			manipulation = entry.get("manipulation") or {}
			previous = manipulation.get("substring_mappings") or []
			if previous != json_safe:
				changed = True

			manipulation.update(
				{
					"substring_mappings": json_safe,
					"effectiveness_score": model.effectiveness_score,
					"method": model.manipulation_method or "smart_substitution",
					"character_strategy": strategy,
				}
			)
			entry["manipulation"] = manipulation

		if changed:
			self.structured_manager.save(run_id, structured)

	def _compute_true_gold(self, question: QuestionManipulation) -> tuple[str | None, float | None]:
		options = question.options_data or {}
		if not options:
			return (None, None)
		if not self.ai_client.is_configured():
			# heuristic fallback
			first_label = next(iter(options.keys()), None)
			return (first_label, 0.5 if first_label else None)
		prompt = f"Question: {question.original_text}\n"
		if options:
			prompt += "Options:\n"
			for k, v in options.items():
				prompt += f"{k}. {v}\n"
		prompt += "\nReturn only the final answer letter."
		res = self.ai_client.call_model(provider="openai:gpt-4o-mini", payload={"prompt": prompt})
		ans = (res or {}).get("response")
		return (str(ans).strip() if ans else None, 0.9 if ans else None)
