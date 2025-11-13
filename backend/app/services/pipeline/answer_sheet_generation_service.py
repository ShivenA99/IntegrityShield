from __future__ import annotations

import json
import logging
import math
import random
import shutil
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Iterable, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

from flask import current_app
from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import AnswerSheetRecord, AnswerSheetRun, AnswerSheetStudent, PipelineRun, QuestionManipulation
from ...utils.exceptions import ResourceNotFound
from ...utils.storage_paths import answer_sheets_directory, run_directory
from ...utils.time import isoformat, utc_now

logger = logging.getLogger(__name__)


@dataclass
class QuestionInfo:
    id: int | None
    number: str
    text: str
    question_type: str
    gold_answer: str
    options: list[dict[str, str]]
    llm_answers: list[dict[str, str]]
    is_subjective: bool
    weighting: float
    raw: QuestionManipulation


class AnswerSheetGenerationService:
    """Simulate student answer sheets for downstream cheating analysis."""

    SUBJECTIVE_TYPES = {
        "short_answer",
        "long_answer",
        "subjective",
        "essay",
        "code",
        "programming",
        "open_response",
        "constructed_response",
    }
    OBJECTIVE_TYPES = {
        "mcq",
        "multiple_choice",
        "true_false",
        "objective",
        "fill_blank",
        "numeric",
    }

    REQUIRED_STAGES = {"smart_reading", "content_discovery", "smart_substitution"}

    def __init__(self, *, session=None) -> None:
        self.session = session or db.session

    def generate(self, run_id: str, config_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        run: PipelineRun | None = (
            PipelineRun.query.options(
                selectinload(PipelineRun.questions),
                selectinload(PipelineRun.stages),
            )
            .filter_by(id=run_id)
            .one_or_none()
        )
        if not run:
            raise ResourceNotFound(f"Pipeline run {run_id} not found")

        self._guard_required_stages(run)

        base_config = deepcopy(current_app.config.get("ANSWER_SHEET_DEFAULTS", {}))
        config = self._merge_config(base_config, config_overrides or {})
        rng = random.Random(config.get("random_seed") or f"{run_id}:{run.created_at or utc_now()}")

        questions = self._extract_questions(run)
        if not questions:
            raise ValueError("No questions available to generate answer sheets.")

        # Remove previous directory if it exists
        answers_root = run_directory(run_id) / "answer_sheets"
        if answers_root.exists():
            shutil.rmtree(answers_root, ignore_errors=True)
        answers_dir = answer_sheets_directory(run_id)

        simulation = self._simulate_answers(run, questions, config, rng)

        existing = AnswerSheetRun.query.filter_by(pipeline_run_id=run_id).one_or_none()
        if existing:
            self.session.delete(existing)
            self.session.flush()

        answer_run = AnswerSheetRun(
            pipeline_run_id=run_id,
            config=config,
            summary=simulation["summary"],
            total_students=len(simulation["students"]),
        )
        self.session.add(answer_run)
        self.session.flush()

        student_models: dict[str, AnswerSheetStudent] = {}
        for student in simulation["students"]:
            model = AnswerSheetStudent(
                run_id=answer_run.id,
                pipeline_run_id=run_id,
                student_key=student["student_key"],
                display_name=student["display_name"],
                is_cheating=student["is_cheating"],
                cheating_strategy=student["strategy"],
                copy_fraction=student["copy_fraction"],
                paraphrase_style=student.get("paraphrase_style"),
                score=student["total_score"],
                metadata_json=student.get("metadata", {}),
            )
            self.session.add(model)
            student_models[student["student_key"]] = model

        self.session.flush()

        record_models: list[AnswerSheetRecord] = []
        for record in simulation["records"]:
            student_model = student_models[record["student_key"]]
            record_models.append(
                AnswerSheetRecord(
                    run_id=answer_run.id,
                    student_id=student_model.id,
                    pipeline_run_id=run_id,
                    question_id=record.get("question_id"),
                    question_number=record["question_number"],
                    question_type=record.get("question_type"),
                    cheating_source=record["cheating_source"],
                    source_reference=record.get("source_reference"),
                    answer_text=record["answer_text"],
                    paraphrased=record["paraphrased"],
                    score=record["score"],
                    confidence=record.get("confidence"),
                    is_correct=record.get("is_correct"),
                    metadata_json=record.get("metadata", {}),
                )
            )

        self.session.add_all(record_models)
        self.session.commit()

        json_payload = {
            "run_id": run_id,
            "generated_at": isoformat(utc_now()),
            "config": config,
            "summary": simulation["summary"],
            "students": simulation["students"],
        }
        json_path = answers_dir / "answer_sheets.json"
        json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

        summary_path = answers_dir / "answer_sheet_summary.json"
        summary_path.write_text(json.dumps(simulation["summary"], indent=2, ensure_ascii=False), encoding="utf-8")

        parquet_path: Optional[str] = None
        if config.get("write_parquet"):
            try:
                import pandas as pd  # type: ignore

                df = pd.DataFrame(simulation["records"])
                parquet_file = answers_dir / "answer_sheets.parquet"
                df.to_parquet(parquet_file, index=False)
                parquet_path = str(parquet_file.relative_to(run_directory(run_id)))
            except ImportError:
                logger.warning("Parquet output requested but pandas is not installed.")
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Failed to write Parquet answer sheets.")

        result = {
            "run_id": run_id,
            "students": len(simulation["students"]),
            "cheating_counts": simulation["summary"]["cheating_counts"],
            "output_files": {
                "json": str(json_path.relative_to(run_directory(run_id))),
                "summary": str(summary_path.relative_to(run_directory(run_id))),
                "parquet": parquet_path,
            },
        }
        return result

    def _guard_required_stages(self, run: PipelineRun) -> None:
        stage_map = {stage.stage_name: stage.status for stage in run.stages}
        missing = sorted(name for name in self.REQUIRED_STAGES if stage_map.get(name) != "completed")
        if missing:
            raise ValueError(
                "Cannot generate answer sheets until prerequisite stages are completed.",
            )

    def _merge_config(self, base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)

        def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
            for key, value in b.items():
                if isinstance(value, dict) and isinstance(a.get(key), dict):
                    a[key] = _merge(deepcopy(a[key]), value)
                else:
                    a[key] = value
            return a

        merged = _merge(merged, overrides)
        self._validate_config(merged)
        breakdown = merged["cheating_breakdown"]
        total = breakdown["llm"] + breakdown["peer"]
        if total <= 0:
            breakdown["llm"] = breakdown["peer"] = 0.5
            total = 1.0
        breakdown["llm"] = breakdown["llm"] / total
        breakdown["peer"] = breakdown["peer"] / total
        return merged

    def _subjective_llm_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        settings = dict(config.get("subjective_llm") or {})
        settings.setdefault("enabled", False)
        return settings

    def _fetch_subjective_llm_answers(
        self,
        *,
        run_id: str,
        questions: list[QuestionInfo],
        config: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        settings = self._subjective_llm_settings(config)
        if not settings.get("enabled"):
            return {}

        if OpenAI is None:
            logger.warning(
                "Subjective LLM generation is enabled but the OpenAI SDK is not installed.",
                extra={"run_id": run_id},
            )
            return {}

        api_key = settings.get("api_key") or current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning(
                "Subjective LLM generation is enabled but no OpenAI API key is configured.",
                extra={"run_id": run_id},
            )
            return {}

        subjective_questions = [q for q in questions if q.is_subjective]
        if not subjective_questions:
            return {}

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        timeout = settings.get("timeout_seconds")
        if timeout:
            try:
                client_kwargs["timeout"] = float(timeout)
            except (TypeError, ValueError):
                logger.debug(
                    "Ignoring invalid subjective LLM timeout: %s", timeout, extra={"run_id": run_id}
                )

        try:
            client = OpenAI(**client_kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to initialize OpenAI client for subjective LLM generation: %s",
                exc,
                extra={"run_id": run_id},
            )
            return {}

        baseline_answers: dict[str, dict[str, Any]] = {}
        model_name = settings.get("model") or "gpt-4o-mini"
        temperature = float(settings.get("temperature", 0.2))
        max_tokens = int(settings.get("max_tokens", 300))

        for question in subjective_questions:
            messages = self._build_subjective_prompt(question)
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "OpenAI call failed for subjective question %s: %s",
                    question.number,
                    exc,
                    extra={"run_id": run_id, "question_number": question.number},
                )
                continue

            answer_text = self._extract_completion_text(response)
            if not answer_text:
                logger.info(
                    "OpenAI returned an empty response for subjective question %s.",
                    question.number,
                    extra={"run_id": run_id, "question_number": question.number},
                )
                continue

            usage_payload: dict[str, Any] = {}
            usage = getattr(response, "usage", None)
            if usage:
                usage_payload = {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
                usage_payload = {k: v for k, v in usage_payload.items() if v is not None}

            baseline_answers[question.number] = {
                "text": answer_text.strip(),
                "model": model_name,
                "base_source": "subjective_llm",
            }
            if usage_payload:
                baseline_answers[question.number]["usage"] = usage_payload

            logger.debug(
                "Generated baseline subjective answer via OpenAI for question %s.",
                question.number,
                extra={"run_id": run_id, "question_number": question.number},
            )

        if baseline_answers:
            logger.info(
                "Generated %s subjective baseline answers with OpenAI model %s.",
                len(baseline_answers),
                model_name,
                extra={"run_id": run_id},
            )
        else:
            logger.warning(
                "No subjective answers were generated by the OpenAI model; falling back to legacy generation.",
                extra={"run_id": run_id},
            )

        return baseline_answers

    def _build_subjective_prompt(self, question: QuestionInfo) -> list[dict[str, str]]:
        question_text = (question.text or "").strip()
        if not question_text:
            question_text = "Provide a thoughtful response to the assessment prompt."

        gold_answer = (question.gold_answer or "").strip()
        instructions = [
            f"You are Student S001 answering Question {question.number} in an assessment.",
            "Respond confidently in natural language with 2-3 concise sentences unless additional detail is required.",
            "Do not mention cheating, AI assistance, or that you are an AI system.",
        ]
        if gold_answer:
            instructions.append(
                "You may use the teacher reference answer for accuracy, but rewrite it in your own words."
            )

        user_content_parts = [
            "\n".join(instructions),
            "",
            "Question prompt:",
            question_text,
        ]
        if gold_answer:
            user_content_parts.extend(
                [
                    "",
                    "Teacher reference answer (do not repeat verbatim):",
                    gold_answer,
                ]
            )

        user_message = "\n".join(part for part in user_content_parts if part is not None).strip()

        return [
            {
                "role": "system",
                "content": (
                    "You are a diligent student providing well-structured, accurate answers to exam questions. "
                    "Write naturally and directly, without markdown formatting, bullet lists, or disclaimers."
                ),
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

    @staticmethod
    def _extract_completion_text(response: Any) -> str:
        if not response:
            return ""

        choices = getattr(response, "choices", None)
        if not choices:
            return ""

        choice = choices[0]
        message = getattr(choice, "message", None)
        if not message:
            return ""

        content = getattr(message, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for segment in content:
                if isinstance(segment, dict) and segment.get("type") == "text":
                    text_value = segment.get("text")
                    if text_value:
                        parts.append(str(text_value))
            return " ".join(parts).strip()

        return ""

    def _validate_config(self, config: dict[str, Any]) -> None:
        total_students = int(config.get("total_students", 0))
        if total_students <= 0:
            raise ValueError("total_students must be a positive integer.")
        cheating_rate = float(config.get("cheating_rate", 0.0))
        if not 0 <= cheating_rate <= 1:
            raise ValueError("cheating_rate must be between 0 and 1.")
        copy_profile = config.get("copy_profile") or {}
        min_frac = float(copy_profile.get("partial_copy_min", 0.0))
        max_frac = float(copy_profile.get("partial_copy_max", 0.0))
        if not (0 <= min_frac <= max_frac <= 1):
            raise ValueError("partial copy range must be between 0 and 1 and min <= max.")
        score_distribution = config.get("score_distribution") or {}
        for key in ("fair", "cheating_llm", "cheating_peer"):
            if key not in score_distribution:
                raise ValueError(f"score_distribution missing '{key}' settings.")

    def _extract_questions(self, run: PipelineRun) -> list[QuestionInfo]:
        structured_questions = {}
        structured = run.structured_data or {}
        for entry in structured.get("questions", []) or []:
            number = str(entry.get("question_number") or entry.get("question_no") or entry.get("q_number") or "")
            if number:
                structured_questions[number] = entry

        questions: list[QuestionInfo] = []
        ordered = sorted(
            run.questions,
            key=lambda q: (
                math.inf if q.sequence_index is None else q.sequence_index,
                self._safe_int(q.question_number),
                q.question_number or "",
            ),
        )
        if not ordered:
            return questions

        question_weight = 100.0 / max(len(ordered), 1)
        for question in ordered:
            number = str(question.question_number or "")
            structured_info = structured_questions.get(number, {})
            options = self._normalize_options(question.options_data, structured_info)
            gold_answer = self._resolve_gold_answer(question, structured_info)
            question_type = (question.question_type or structured_info.get("question_type") or "unknown").lower()
            if question_type in {"true_false", "true/false", "truefalse"} and not options:
                options = [
                    {"label": "True", "text": "True"},
                    {"label": "False", "text": "False"},
                ]
            llm_answers = self._extract_llm_answers(question, structured_info)
            questions.append(
                QuestionInfo(
                    id=question.id,
                    number=number or str(len(questions) + 1),
                    text=question.original_text or structured_info.get("stem_text") or "",
                    question_type=question_type,
                    gold_answer=gold_answer,
                    options=options,
                    llm_answers=llm_answers,
                    is_subjective=self._is_subjective(question_type, options),
                    weighting=question_weight,
                    raw=question,
                )
            )
        return questions

    def _simulate_answers(
        self,
        run: PipelineRun,
        questions: list[QuestionInfo],
        config: dict[str, Any],
        rng: random.Random,
    ) -> dict[str, Any]:
        total_students = int(config["total_students"])
        cheating_rate = float(config["cheating_rate"])
        total_cheaters = max(0, min(total_students, round(total_students * cheating_rate)))
        llm_count = min(total_cheaters, round(total_cheaters * config["cheating_breakdown"]["llm"]))
        peer_count = total_cheaters - llm_count
        fair_count = total_students - total_cheaters

        strategies = ["fair"] * fair_count + ["cheating_llm"] * llm_count + ["cheating_peer"] * peer_count
        baseline_student_key = "S001"
        baseline_subjective_answers = self._fetch_subjective_llm_answers(
            run_id=run.id,
            questions=questions,
            config=config,
        )

        rng.shuffle(strategies)
        forced_baseline_strategy = False
        if strategies:
            if strategies[0] != "fair":
                forced_baseline_strategy = True
            strategies[0] = "fair"
        if forced_baseline_strategy:
            logger.info(
                "Adjusted strategy distribution to ensure baseline student S001 is fair for subjective LLM seeding.",
                extra={"run_id": run.id},
            )

        llm_models = self._collect_llm_models(run=run, questions=questions)
        students_output: list[dict[str, Any]] = []
        records_flat: list[dict[str, Any]] = []
        student_record_lookup: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

        for index, strategy in enumerate(strategies, start=1):
            student_key = f"S{index:03d}"
            student_data, student_records = self._simulate_student(
                student_key=student_key,
                strategy=strategy,
                questions=questions,
                config=config,
                rng=rng,
                student_record_lookup=student_record_lookup,
                completed_students=students_output,
                llm_models=llm_models,
                baseline_subjective_answers=baseline_subjective_answers,
                baseline_student_key=baseline_student_key,
                run_id=run.id,
            )
            students_output.append(student_data)
            for record in student_records:
                records_flat.append(record)
                student_record_lookup[student_key][record["question_number"]] = record

        summary = self._build_summary(students_output, config, fair_count, llm_count, peer_count)
        return {
            "students": students_output,
            "records": records_flat,
            "summary": summary,
        }

    def _simulate_student(
        self,
        *,
        student_key: str,
        strategy: str,
        questions: list[QuestionInfo],
        config: dict[str, Any],
        rng: random.Random,
        student_record_lookup: dict[str, dict[str, dict[str, Any]]],
        completed_students: list[dict[str, Any]],
        llm_models: list[str],
        baseline_subjective_answers: dict[str, dict[str, Any]] | None,
        baseline_student_key: str | None,
        run_id: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        distribution = config["score_distribution"][strategy]
        target_score = self._clamp(
            rng.gauss(distribution["mean"], distribution["stddev"]),
            distribution["min"],
            distribution["max"],
        )
        question_weight = questions[0].weighting if questions else 0.0
        num_correct = max(0, min(len(questions), round(target_score / question_weight if question_weight else 0)))
        correct_questions = set(rng.sample([q.number for q in questions], k=num_correct)) if questions else set()

        ability_targets = self._build_ability_targets(
            questions=questions,
            correct_questions=correct_questions,
            target_score=target_score,
            strategy=strategy,
            rng=rng,
        )

        copy_fraction = 0.0
        copy_questions: set[str] = set()
        source_student_key: Optional[str] = None

        baseline_answers = baseline_subjective_answers or {}
        is_baseline_student = bool(baseline_student_key and student_key == baseline_student_key)

        if strategy == "cheating_llm":
            copy_fraction = 1.0
            copy_questions = {q.number for q in questions}
        elif strategy == "cheating_peer":
            copy_settings = config["copy_profile"]
            if rng.random() < copy_settings["full_copy_probability"]:
                copy_fraction = 1.0
                copy_questions = {q.number for q in questions}
            else:
                copy_fraction = rng.uniform(copy_settings["partial_copy_min"], copy_settings["partial_copy_max"])
                copy_count = max(1, int(round(copy_fraction * len(questions))))
                copy_questions = set(rng.sample([q.number for q in questions], k=copy_count))
            viable_sources = [student for student in completed_students if student["student_key"] != student_key]
            if viable_sources:
                source_student_key = rng.choice(viable_sources)["student_key"]

        student_records: list[dict[str, Any]] = []
        paraphrase_probability = float(config.get("paraphrase_probability", 0.0))
        for question in questions:
            should_copy = question.number in copy_questions
            paraphrased = False
            cheating_source = "fair"
            source_reference: Optional[str] = None
            metadata: dict[str, Any] = {}
            ability_target = ability_targets.get(question.number)
            if ability_target is not None:
                metadata["ability_target"] = round(ability_target, 3)

            if strategy == "cheating_llm" and should_copy:
                cheating_source = "llm"
                llm_answer = self._choose_llm_answer(question, rng, llm_models)
                answer_text = llm_answer.get("text")
                metadata.update({"llm_model": llm_answer.get("model")})
                is_correct = True
            elif strategy == "cheating_peer" and should_copy:
                cheating_source = "peer"
                source_reference = source_student_key
                source_record = (
                    student_record_lookup.get(source_student_key or "", {}).get(question.number)
                    if source_student_key
                    else None
                )
                if source_record:
                    answer_text = source_record["answer_text"]
                    is_correct = bool(source_record.get("is_correct"))
                    metadata.update({"copied_from": source_student_key})
                else:
                    answer_text = None
                    is_correct = question.number in correct_questions
            else:
                answer_text = None
                is_correct = question.number in correct_questions

            baseline_entry: Optional[dict[str, Any]] = None
            if question.is_subjective and baseline_answers:
                baseline_entry = baseline_answers.get(question.number)

            if (
                answer_text is None
                and baseline_entry
                and is_baseline_student
            ):
                baseline_text = str(baseline_entry.get("text") or "").strip()
                if baseline_text:
                    answer_text = baseline_text
                    metadata["base_source"] = baseline_entry.get("base_source", "subjective_llm")
                    metadata["transformation"] = "subjective_llm_direct"
                    metadata["subjective_llm_seed"] = True
                    model_name = baseline_entry.get("model")
                    if model_name:
                        metadata["llm_model"] = model_name
                    usage_payload = baseline_entry.get("usage")
                    if usage_payload:
                        metadata["llm_usage"] = usage_payload
                else:
                    baseline_entry = None

            if answer_text is None:
                generation = self._generate_answer_text(
                    question=question,
                    is_correct=is_correct,
                    rng=rng,
                    strategy=strategy,
                    ability_target=ability_target,
                    student_record_lookup=student_record_lookup,
                    completed_students=completed_students,
                    baseline_subjective_answers=baseline_answers,
                )
                answer_text = generation["text"]
                metadata_updates = {
                    "base_source": generation.get("base_source"),
                    "paraphrase_strength": generation.get("paraphrase_strength"),
                    "ability_target": generation.get("ability_target"),
                    "transformation": generation.get("transformation"),
                    "baseline_model": generation.get("baseline_model"),
                    "baseline_usage": generation.get("baseline_usage"),
                }
                metadata.update({k: v for k, v in metadata_updates.items() if v is not None})
                if generation.get("base_source") == "subjective_llm":
                    metadata.setdefault("subjective_llm_seed", True)
                baseline_model_name = generation.get("baseline_model")
                if baseline_model_name and "llm_model" not in metadata:
                    metadata["llm_model"] = baseline_model_name
                baseline_usage = generation.get("baseline_usage")
                if baseline_usage and "llm_usage" not in metadata:
                    metadata["llm_usage"] = baseline_usage

            if question.is_subjective and strategy != "fair" and rng.random() < paraphrase_probability:
                paraphrased = True
                answer_text = self._paraphrase_text(answer_text, rng)
                metadata["extra_paraphrase"] = True

            confidence = self._determine_confidence(strategy, is_correct, rng)
            question_score = question.weighting if is_correct else 0.0

            record_payload = {
                "pipeline_run_id": run_id,
                "student_key": student_key,
                "question_id": question.id,
                "question_number": question.number,
                "question_type": question.question_type,
                "cheating_source": cheating_source,
                "source_reference": source_reference,
                "answer_text": answer_text,
                "paraphrased": paraphrased,
                "score": question_score,
                "confidence": confidence,
                "is_correct": is_correct,
                "metadata": metadata,
            }
            student_records.append(record_payload)

        total_score = sum(record["score"] for record in student_records)
        correct_count = sum(1 for record in student_records if record["is_correct"])
        paraphrased_count = sum(1 for record in student_records if record["paraphrased"])

        student_payload = {
            "student_key": student_key,
            "display_name": f"Student {student_key}",
            "strategy": strategy,
            "is_cheating": strategy != "fair",
            "copy_fraction": round(copy_fraction, 3),
            "paraphrase_style": "subjective_only" if paraphrased_count else None,
            "total_score": round(total_score, 2),
            "correct_answers": correct_count,
            "records": student_records,
            "metadata": {
                "target_score": round(target_score, 2),
                "copied_question_numbers": sorted(copy_questions),
                "paraphrased_count": paraphrased_count,
                "source_student": source_student_key,
            },
        }

        if is_baseline_student and baseline_answers:
            baseline_model = next(
                (entry.get("model") for entry in baseline_answers.values() if entry.get("model")), None
            )
            seeded_questions = sorted(
                question_number
                for question_number, entry in baseline_answers.items()
                if entry.get("text")
            )
            if baseline_model:
                student_payload["metadata"]["subjective_llm_model"] = baseline_model
            if seeded_questions:
                student_payload["metadata"]["subjective_llm_seeded_questions"] = seeded_questions

        return student_payload, student_records

    def _build_summary(
        self,
        students: list[dict[str, Any]],
        config: dict[str, Any],
        fair_count: int,
        llm_count: int,
        peer_count: int,
    ) -> dict[str, Any]:
        total_scores = [student["total_score"] for student in students]
        summary = {
            "total_students": len(students),
            "cheating_counts": {
                "total": llm_count + peer_count,
                "llm": llm_count,
                "peer": peer_count,
                "fair": fair_count,
            },
            "score_statistics": self._score_stats(total_scores),
            "strategy_breakdown": {},
            "config_snapshot": config,
        }

        by_strategy = defaultdict(list)
        for student in students:
            by_strategy[student["strategy"]].append(student["total_score"])

        for strategy, scores in by_strategy.items():
            summary["strategy_breakdown"][strategy] = {
                "count": len(scores),
                "score_stats": self._score_stats(scores),
            }
        return summary

    def _collect_llm_models(self, run: PipelineRun, questions: list[QuestionInfo]) -> list[str]:
        models = list(run.pipeline_config.get("ai_models", []) or [])
        for question in questions:
            for variant in question.llm_answers:
                model = variant.get("model")
                if model and model not in models:
                    models.append(model)
        return models

    @staticmethod
    def _clamp(value: float, min_value: float, max_value: float) -> float:
        return max(min_value, min(max_value, value))

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return math.inf

    def _normalize_options(self, options_data: Any, structured_info: dict[str, Any]) -> list[dict[str, str]]:
        if not options_data and structured_info.get("options"):
            options_data = structured_info["options"]
        normalized: list[dict[str, str]] = []
        if isinstance(options_data, dict):
            for key, val in options_data.items():
                normalized.append({"label": str(key), "text": str(val)})
        elif isinstance(options_data, list):
            for entry in options_data:
                if isinstance(entry, dict):
                    label = entry.get("label") or entry.get("option") or entry.get("id")
                    text = entry.get("text") or entry.get("value") or entry.get("content")
                    normalized.append({"label": str(label or len(normalized) + 1), "text": str(text or "")})
                else:
                    normalized.append({"label": str(len(normalized) + 1), "text": str(entry)})
        elif isinstance(options_data, str):
            parts = [part.strip() for part in options_data.split("\n") if part.strip()]
            normalized = [{"label": chr(65 + idx), "text": part} for idx, part in enumerate(parts)]
        return normalized

    def _resolve_gold_answer(
        self,
        question: QuestionManipulation,
        structured_info: dict[str, Any],
    ) -> str:
        gold = question.gold_answer or structured_info.get("gold_answer") or ""
        if isinstance(gold, dict):
            return str(gold.get("text") or gold.get("answer") or "")
        return str(gold)

    def _extract_llm_answers(
        self,
        question: QuestionManipulation,
        structured_info: dict[str, Any],
    ) -> list[dict[str, str]]:
        answers: list[dict[str, str]] = []
        candidates = []
        if isinstance(question.ai_model_results, dict):
            candidates.append(question.ai_model_results)
        answer_bank = (
            (((structured_info.get("manipulation") or {}).get("ai_answer_bank")) or structured_info.get("ai_answer_bank"))
            if structured_info
            else None
        )
        if isinstance(answer_bank, dict):
            candidates.append(answer_bank)
        for candidate in candidates:
            for model_name, payload in candidate.items():
                if isinstance(payload, dict):
                    text = payload.get("manipulated_answer") or payload.get("answer") or payload.get("text")
                    if text:
                        answers.append({"model": str(model_name), "text": str(text)})
        return answers

    def _is_subjective(self, question_type: str, options: list[dict[str, str]]) -> bool:
        if question_type in self.SUBJECTIVE_TYPES:
            return True
        if question_type in self.OBJECTIVE_TYPES:
            return False
        if options:
            return False
        return True

    def _choose_llm_answer(
        self,
        question: QuestionInfo,
        rng: random.Random,
        llm_models: Iterable[str],
    ) -> dict[str, str]:
        if question.llm_answers:
            return rng.choice(question.llm_answers)
        model_list = list(llm_models)
        model_name = rng.choice(model_list) if model_list else "synthetic-llm"
        if question.options:
            label = self._render_correct_option_label(question)
            text = self._format_option_answer(question, label)
        elif question.gold_answer:
            text = question.gold_answer
        else:
            text = f"Correct response for question {question.number}"
        return {
            "model": model_name,
            "text": text,
        }

    def _build_ability_targets(
        self,
        *,
        questions: list[QuestionInfo],
        correct_questions: set[str],
        target_score: float,
        strategy: str,
        rng: random.Random,
    ) -> dict[str, float]:
        if not questions:
            return {}
        overall_skill = self._clamp(target_score / 100.0, 0.0, 1.0)
        ability_targets: dict[str, float] = {}
        for question in questions:
            if question.number in correct_questions:
                base_target = 0.6 + (0.4 * overall_skill)
            else:
                base_target = 0.2 + (0.3 * overall_skill)
            if strategy == "cheating_llm":
                base_target = self._clamp(base_target + 0.15, 0.05, 0.98)
            elif strategy == "cheating_peer":
                base_target = self._clamp(base_target - 0.1, 0.02, 0.9)
            jitter = rng.uniform(-0.08, 0.08)
            ability_targets[question.number] = self._clamp(base_target + jitter, 0.01, 0.99)
        return ability_targets

    def _select_subjective_base_text(
        self,
        *,
        question: QuestionInfo,
        strategy: str,
        rng: random.Random,
        student_record_lookup: dict[str, dict[str, dict[str, Any]]],
        completed_students: list[dict[str, Any]],
    ) -> tuple[Optional[str], Optional[str]]:
        if strategy == "cheating_llm" and question.llm_answers:
            candidate = rng.choice(question.llm_answers)
            text = str(candidate.get("text") or "").strip()
            if text:
                return text, "llm"

        if strategy == "cheating_peer":
            peer_candidates: list[str] = []
            for student in completed_students:
                record = student_record_lookup.get(student["student_key"], {}).get(question.number)
                if record:
                    answer_text = str(record.get("answer_text") or "").strip()
                    if answer_text:
                        peer_candidates.append(answer_text)
            if peer_candidates:
                return rng.choice(peer_candidates), "peer"
            if question.llm_answers:
                candidate = rng.choice(question.llm_answers)
                text = str(candidate.get("text") or "").strip()
                if text:
                    return text, "llm"

        if question.gold_answer:
            return str(question.gold_answer), "gold"

        if question.llm_answers:
            candidate = rng.choice(question.llm_answers)
            text = str(candidate.get("text") or "").strip()
            if text:
                return text, "llm"

        if question.text:
            return str(question.text), "question_stem"

        return None, None

    def _render_subjective_variation(
        self,
        *,
        base_text: str,
        is_correct: bool,
        paraphrase_strength: float,
        ability_target: float,
        strategy: str,
        rng: random.Random,
    ) -> tuple[str, str]:
        base_clean = base_text.strip()
        focus = self._focus_phrase(base_clean)
        if not focus:
            focus = "the topic"

        if is_correct:
            if paraphrase_strength >= 0.7:
                lead_in = rng.choice(
                    ["Fundamentally,", "In summary,", "Ultimately,", "In practical terms,"]
                )
                connector = rng.choice(
                    [
                        "This highlights why {} is central.",
                        "That reinforces the importance of {}.",
                        "It clearly ties back to {}.",
                    ]
                )
                text = f"{lead_in} {self._normalize_sentence(base_clean)} {connector.format(focus)}"
                return text.strip(), "subjective_enhanced"
            if paraphrase_strength >= 0.45:
                return self._paraphrase_text(base_clean, rng), "subjective_paraphrased"
            concise = f"Short answer: {focus}"
            return self._normalize_sentence(concise), "subjective_concise"

        confusion_topics = [
            "a different theorem",
            "the previous topic",
            "an unrelated example",
            "another definition",
            "the alternate dataset",
        ]
        confusion = rng.choice(confusion_topics)
        prefix_map = {
            "cheating_llm": [
                "The model suggested",
                "The AI response indicated",
                "The LLM answer leaned toward",
            ],
            "cheating_peer": [
                "The notes I copied said",
                "What I saw from a peer was",
                "Someone else's answer mentioned",
            ],
            "fair": ["I guessed", "I assumed", "I thought"],
        }
        prefixes = prefix_map.get(strategy, prefix_map["fair"])
        prefix = rng.choice(prefixes)

        severity = self._clamp((1.0 - paraphrase_strength) * 0.7 + (1.0 - ability_target) * 0.3, 0.0, 1.0)
        if severity > 0.65:
            text = f"{prefix} it might be {confusion}, but I'm really not confident."
            return self._normalize_sentence(text), "subjective_incorrect_unsure"
        if severity > 0.35:
            text = f"{prefix} {confusion}, even though I kept thinking about {focus}."
            return self._normalize_sentence(text), "subjective_incorrect_mixed"
        text = f"{prefix} {confusion}. I mixed it up with how {focus} works."
        return self._normalize_sentence(text), "subjective_incorrect_confident"

    @staticmethod
    def _normalize_sentence(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return ""
        if cleaned[-1] not in ".!?":
            return f"{cleaned}."
        return cleaned

    @staticmethod
    def _focus_phrase(text: str) -> str:
        cleaned = " ".join(text.strip().split())
        if not cleaned:
            return ""
        if len(cleaned) <= 96:
            return cleaned
        truncated = cleaned[:96]
        last_space = truncated.rfind(" ")
        if last_space > 40:
            truncated = truncated[:last_space]
        return truncated.strip() + "..."

    def _generate_answer_text(
        self,
        *,
        question: QuestionInfo,
        is_correct: bool,
        rng: random.Random,
        strategy: str,
        ability_target: Optional[float],
        student_record_lookup: dict[str, dict[str, dict[str, Any]]],
        completed_students: list[dict[str, Any]],
        baseline_subjective_answers: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "text": "",
            "base_source": None,
            "paraphrase_strength": None,
            "transformation": None,
            "ability_target": round(ability_target, 3) if ability_target is not None else None,
        }

        baseline_entry: Optional[dict[str, Any]] = None
        if question.is_subjective and baseline_subjective_answers:
            baseline_entry = baseline_subjective_answers.get(question.number)

        if question.options:
            if is_correct:
                chosen_label = self._render_correct_option_label(question)
            else:
                chosen_label = self._choose_incorrect_option_label(question, rng)
            result["text"] = self._format_option_answer(question, chosen_label)
            result["base_source"] = "options"
            result["transformation"] = "objective_selection"
            return result
        if not question.gold_answer and not question.is_subjective:
            result["text"] = "No answer provided."
            result["base_source"] = "empty"
            result["transformation"] = "missing_gold"
            return result
        if is_correct:
            if not question.is_subjective:
                result["text"] = question.gold_answer
                result["base_source"] = "gold"
                result["transformation"] = "objective_direct"
                return result
        else:
            if not question.is_subjective:
                result["text"] = "Incorrect response based on misunderstanding of the concept."
                result["transformation"] = "objective_default_incorrect"
                return result

        if question.is_subjective:
            base_text = ""
            base_source: Optional[str] = None
            baseline_used = False
            if baseline_entry:
                candidate_text = str(baseline_entry.get("text") or "").strip()
                if candidate_text:
                    base_text = candidate_text
                    base_source = baseline_entry.get("base_source") or "subjective_llm"
                    baseline_used = True

            if not base_text:
                base_text, base_source = self._select_subjective_base_text(
                    question=question,
                    strategy=strategy,
                    rng=rng,
                    student_record_lookup=student_record_lookup,
                    completed_students=completed_students,
                )
            if not base_text:
                base_text = question.gold_answer or ""
            base_text = base_text.strip()
            if not base_text:
                result["text"] = "No answer provided."
                result["base_source"] = base_source or "empty"
                result["transformation"] = "subjective_empty"
                return result

            ability_value = self._clamp(ability_target if ability_target is not None else 0.5, 0.01, 0.99)
            alpha = 0.8 + (ability_value * 4.0)
            beta = 0.8 + ((1.0 - ability_value) * 4.0)
            paraphrase_strength = rng.betavariate(alpha, beta)

            rendered_text, transformation = self._render_subjective_variation(
                base_text=base_text,
                is_correct=is_correct,
                paraphrase_strength=paraphrase_strength,
                ability_target=ability_value,
                strategy=strategy,
                rng=rng,
            )

            result["text"] = rendered_text
            result["base_source"] = base_source
            result["paraphrase_strength"] = round(paraphrase_strength, 3)
            result["transformation"] = transformation
            result["ability_target"] = round(ability_value, 3)
            if baseline_used and baseline_entry:
                baseline_model = baseline_entry.get("model")
                if baseline_model:
                    result["baseline_model"] = baseline_model
                usage_payload = baseline_entry.get("usage")
                if usage_payload:
                    result["baseline_usage"] = usage_payload
            return result

        result["text"] = question.gold_answer if is_correct else "Incorrect response based on misunderstanding of the concept."
        result["base_source"] = "gold"
        result["transformation"] = "objective_fallback"
        return result

    def _render_correct_option_label(self, question: QuestionInfo) -> str:
        gold = (question.gold_answer or "").strip()
        if not gold:
            return question.options[0]["label"]
        gold_upper = gold.upper()
        for option in question.options:
            label = str(option.get("label") or "").strip()
            text = str(option.get("text") or "")
            if label.upper() == gold_upper:
                return label
            if text and text.lower() in gold.lower():
                return label
        return gold

    def _choose_incorrect_option_label(self, question: QuestionInfo, rng: random.Random) -> str:
        labels = [opt["label"] for opt in question.options if opt.get("label")]
        if not labels:
            return "N/A"
        correct_label = self._render_correct_option_label(question)
        wrong_options = [label for label in labels if label != correct_label]
        if not wrong_options:
            return labels[0]
        return rng.choice(wrong_options)

    def _format_option_answer(self, question: QuestionInfo, label: str) -> str:
        label_clean = str(label).strip()
        for option in question.options:
            option_label = str(option.get("label") or "").strip()
            option_text = str(option.get("text") or "").strip()
            if option_label.upper() == label_clean.upper():
                if not option_text or option_text.upper() == option_label.upper():
                    return option_label or option_text
                if option_label:
                    prefix = f"{option_label}." if option_label else ""
                    return f"{prefix} {option_text}".strip()
                return option_text
        return label_clean

    def _paraphrase_text(self, text: str, rng: random.Random) -> str:
        if not text:
            return text
        templates = [
            "In essence, {}",
            "To put it differently, {}",
            "A concise explanation is that {}",
            "{} (rephrased for clarity)",
        ]
        template = rng.choice(templates)
        return template.format(text.rstrip(".") + ".")

    def _determine_confidence(self, strategy: str, is_correct: bool, rng: random.Random) -> float:
        base = 0.85 if is_correct else 0.45
        if strategy == "cheating_llm":
            base += 0.1
        elif strategy == "cheating_peer":
            base -= 0.05
        variance = rng.uniform(-0.08, 0.08)
        return round(self._clamp(base + variance, 0.0, 1.0), 3)

    def _score_stats(self, scores: list[float]) -> dict[str, Any]:
        if not scores:
            return {"average": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
        avg = mean(scores)
        std = pstdev(scores) if len(scores) > 1 else 0.0
        return {
            "average": round(avg, 2),
            "stdev": round(std, 2),
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
        }

