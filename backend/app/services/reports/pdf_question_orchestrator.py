from __future__ import annotations

import asyncio
import json
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from flask import current_app

from ...utils.logging import get_logger
from .llm_clients import BaseLLMClient, LLMClientError, build_available_clients

logger = get_logger(__name__)


@dataclass
class QuestionPrompt:
    question_id: int | None
    question_number: str
    question_text: str
    question_type: str | None = None
    options: list[dict[str, str]] | None = None
    gold_answer: str | None = None


class PDFQuestionEvaluator:
    """Upload a PDF to all configured providers and ask each question."""

    def __init__(self, *, prompts: list[str]) -> None:
        if not prompts:
            raise ValueError("At least one prompt is required for LLM evaluation.")
        self.prompts = prompts

    def _clients(self, config_dict: dict[str, Any] | None = None) -> dict[str, BaseLLMClient]:
        if config_dict is None:
            cfg = current_app.config
        else:
            cfg = config_dict
        clients = build_available_clients(
            openai_key=cfg.get("OPENAI_API_KEY"),
            anthropic_key=cfg.get("ANTHROPIC_API_KEY"),
            google_key=cfg.get("GOOGLE_AI_KEY"),
            grok_key=cfg.get("GROK_API_KEY"),
            model_overrides=cfg.get("LLM_REPORT_MODEL_OVERRIDES") or {},
            fallback_models=cfg.get("LLM_REPORT_MODEL_FALLBACKS") or {},
        )
        if not clients:
            raise ValueError(
                "No report providers are configured. Supply at least one API key for OpenAI, Anthropic, Google, or Grok."
            )
        return clients

    def evaluate(self, pdf_path: str, questions: list[QuestionPrompt]) -> dict[str, Any]:
        # Extract Flask config before threading to avoid "Working outside of application context" error
        config_dict = {
            "OPENAI_API_KEY": current_app.config.get("OPENAI_API_KEY"),
            "ANTHROPIC_API_KEY": current_app.config.get("ANTHROPIC_API_KEY"),
            "GOOGLE_AI_KEY": current_app.config.get("GOOGLE_AI_KEY"),
            "GROK_API_KEY": current_app.config.get("GROK_API_KEY"),
            "LLM_REPORT_MODEL_OVERRIDES": current_app.config.get("LLM_REPORT_MODEL_OVERRIDES") or {},
            "LLM_REPORT_MODEL_FALLBACKS": current_app.config.get("LLM_REPORT_MODEL_FALLBACKS") or {},
        }

        try:
            # Check if there's already a running event loop
            asyncio.get_running_loop()
            # We're in an async context - run in a separate thread to avoid blocking
            import threading

            result_container = {}
            error_container = {}

            def run_in_thread():
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(self._evaluate_async(pdf_path, questions, config_dict))
                    result_container['result'] = result
                except Exception as e:
                    error_container['error'] = e
                finally:
                    loop.close()

            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=300)  # 5 minute timeout

            if thread.is_alive():
                raise TimeoutError("LLM evaluation timed out after 5 minutes")
            if 'error' in error_container:
                raise error_container['error']
            return result_container.get('result', {})

        except RuntimeError:
            # No running loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._evaluate_async(pdf_path, questions, config_dict))
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    async def _evaluate_async(self, pdf_path: str, questions: list[QuestionPrompt], config_dict: dict[str, Any] | None = None) -> dict[str, Any]:
        clients = self._clients(config_dict)
        uploads = await self._upload_to_providers(clients, pdf_path)
        # Normalize question numbers for consistent matching
        def normalize_q_num(q_num: str) -> str:
            try:
                return str(int(q_num))
            except (ValueError, TypeError):
                return str(q_num).strip()
        
        question_responses: dict[str, list[dict[str, Any]]] = {
            normalize_q_num(q.question_number): [] for q in questions
        }

        # Create tasks for all providers to run in parallel
        tasks = []
        provider_names = []
        for provider_name, client in clients.items():
            file_ref = uploads.get(provider_name)
            task = self._ask_all_questions(client, provider_name, file_ref, questions)
            tasks.append(task)
            provider_names.append(provider_name)

        # Execute all provider queries in parallel
        logger.info("Querying %d providers in parallel for %d questions", len(tasks), len(questions))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results from all providers
        for provider_name, result in zip(provider_names, results):
            if isinstance(result, Exception):
                logger.error("Provider %s failed: %s", provider_name, result)
                continue

            # result is the batched_answers list
            for answer in result:
                q_number = answer.get("question_number")
                # Normalize question number to string for consistent matching
                if q_number is not None:
                    try:
                        # Try to normalize: convert to int then back to string to remove leading zeros
                        q_number = str(int(q_number))
                    except (ValueError, TypeError):
                        q_number = str(q_number).strip()
                else:
                    q_number = None
                
                if q_number and q_number not in question_responses:
                    expected_numbers = sorted(question_responses.keys(), key=lambda x: int(x) if x.isdigit() else 999)
                    logger.warning(
                        "Provider %s returned unknown question number %s (expected: %s). "
                        "This answer will be dropped.",
                        provider_name, q_number, expected_numbers
                    )
                    continue
                if q_number:
                    question_responses[q_number].append(answer)
        
        aggregated = []
        for question in questions:
            # Normalize question number for lookup to match normalized provider responses
            q_num_normalized = normalize_q_num(question.question_number)
            
            answers = question_responses.get(q_num_normalized, [])
            if not answers:
                logger.warning(
                    "Question %s (normalized: %s) has no answers. Available keys: %s",
                    question.question_number, q_num_normalized, sorted(question_responses.keys())
                )
            
            aggregated.append(
                {
                    "question_id": question.question_id,
                    "question_number": question.question_number,
                    "question_text": question.question_text,
                    "question_type": question.question_type,
                    "options": question.options or [],
                    "gold_answer": question.gold_answer,
                    "answers": answers,
                }
            )

        return {
            "providers": list(clients.keys()),
            "questions": aggregated,
        }

    async def _upload_to_providers(self, clients: dict[str, BaseLLMClient], pdf_path: str) -> dict[str, str | None]:
        """Upload PDF to all providers concurrently with stagger delay to prevent thundering herd."""
        async def upload_with_delay(name: str, client: BaseLLMClient, delay: float) -> tuple[str, str | None]:
            await asyncio.sleep(delay)
            try:
                file_ref = await client.upload_file(pdf_path)
                logger.info("Successfully uploaded PDF to %s", name)
                return name, file_ref
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to upload PDF to %s: %s", name, exc)
                return name, None

        # Stagger uploads by 300ms to avoid thundering herd (conservative for unknown API tier)
        tasks = [
            upload_with_delay(name, client, idx * 0.3)
            for idx, (name, client) in enumerate(clients.items())
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        uploads: dict[str, str | None] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error("Upload exception: %s", result)
                continue
            name, file_ref = result
            uploads[name] = file_ref

        return uploads

    async def _ask_all_questions(
        self,
        client: BaseLLMClient,
        provider_name: str,
        file_ref: str | None,
        questions: list[QuestionPrompt],
    ) -> list[dict[str, Any]]:
        payload = self._build_batch_prompt(provider_name, questions)
        try:
            # Don't pass question_data to provider file upload calls - it's only needed for scoring
            # The prompt already contains all question information
            raw = await client.query_with_file(
                file_ref, payload["prompt"], question_data=None
            )
        except (LLMClientError, Exception) as exc:  # noqa: BLE001
            logger.warning("Provider %s failed batch evaluation: %s", provider_name, exc)
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": None,
                    "success": False,
                    "error": str(exc),
                }
                for question in questions
            ]

        try:
            extracted = self._extract_json_payload(raw)
            parsed = json.loads(extracted)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Provider %s returned invalid JSON: %s. Raw response (first 500 chars): %s",
                provider_name,
                exc,
                raw[:500] if raw else "None",
            )
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": raw,
                    "success": False,
                    "error": f"Invalid JSON payload: {str(exc)}",
                }
                for question in questions
            ]

        answers = parsed.get("answers") if isinstance(parsed, dict) else None
        if not isinstance(answers, list):
            logger.warning("Provider %s returned JSON without 'answers' list.", provider_name)
            return [
                {
                    "provider": provider_name,
                    "question_number": question.question_number,
                    "answer_label": None,
                    "answer_text": None,
                    "confidence": None,
                    "raw_answer": parsed,
                    "success": False,
                    "error": "Missing answers",
                }
                for question in questions
            ]

        normalized_answers: dict[str, dict[str, Any]] = {}
        for answer in answers:
            q_number_raw = answer.get("question_number")
            # Normalize question number: convert to int then string to ensure consistent format
            if q_number_raw is not None:
                try:
                    q_number = str(int(q_number_raw))
                except (ValueError, TypeError):
                    q_number = str(q_number_raw).strip()
            else:
                q_number = None
            
            if not q_number:
                logger.warning(
                    "Provider %s returned answer with missing/invalid question_number: %s",
                    provider_name, answer
                )
                continue
            
            normalized_answers[q_number] = {
                "provider": provider_name,
                "question_number": q_number,
                "answer_label": self._safe_str(answer.get("answer_label")),
                "answer_text": self._safe_str(answer.get("answer_text")),
                "confidence": self._safe_float(answer.get("confidence")),
                "raw_answer": answer,
                "success": True,
                "error": None,
            }

        results: list[dict[str, Any]] = []
        for question in questions:
            # Normalize question number for lookup
            q_num_normalized = question.question_number
            try:
                q_num_normalized = str(int(question.question_number))
            except (ValueError, TypeError):
                q_num_normalized = str(question.question_number).strip()
            
            entry = normalized_answers.get(q_num_normalized)
            if entry:
                results.append(entry)
            else:
                # Log missing answers for debugging
                available_numbers = sorted(normalized_answers.keys(), key=lambda x: int(x) if x.isdigit() else 999)
                logger.debug(
                    "Provider %s missing answer for question %s (available: %s)",
                    provider_name, question.question_number, available_numbers
                )
                results.append(
                    {
                        "provider": provider_name,
                        "question_number": question.question_number,
                        "answer_label": None,
                        "answer_text": None,
                        "confidence": None,
                        "raw_answer": None,
                        "success": False,
                        "error": "Missing entry in provider response",
                    }
                )
        return results

    @staticmethod
    def _extract_json_payload(raw: Any) -> str:
        """Extract JSON from response, handling markdown code fences."""
        if not isinstance(raw, str):
            return str(raw) if raw else ""
        text = raw.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1 :]
            closing = text.rfind("```")
            if closing != -1:
                text = text[:closing]
        text = text.strip()
        if not text:
            return text

        start_char = None
        start_idx = -1
        for candidate in ("{", "["):
            idx = text.find(candidate)
            if idx != -1 and (start_idx == -1 or idx < start_idx):
                start_idx = idx
                start_char = candidate
        if start_idx > 0:
            text = text[start_idx:]
        elif start_idx == -1:
            return text

        end_char = "}" if start_char == "{" else "]" if start_char == "[" else None
        if end_char:
            end_idx = text.rfind(end_char)
            if end_idx != -1:
                text = text[: end_idx + 1]

        return text.strip()

    def _build_batch_prompt(self, provider_name: str, questions: list[QuestionPrompt]) -> dict[str, Any]:
        prompt_lines = [
            "You will analyze an attached PDF assessment and answer multiple questions as accurately as possible.",
            "Work through the questions sequentially: first solve each question one by one using the PDF, then format your final responses in the required JSON schema.",
            "Answer every question; do not skip any.",
            "",
            "REQUIRED JSON SCHEMA:",
            "{",
            '  "provider": "<provider_name>",',
            '  "answers": [',
            '    {',
            '      "question_number": "string (MUST be exactly as shown in questions below, e.g., \"1\", \"2\", \"9\", \"10\")",',
            '      "answer_label": "string or null (single letter for MCQ, e.g., \"A\" or \"B\")",',
            '      "answer_text": "string or null (full option text or answer)",',
            '      "confidence": "number (0-1)",',
            '      "rationale": "string or null"',
            '    }',
            '  ]',
            "}",
            "",
            "CRITICAL FORMAT RULES:",
            "",
            "QUESTION NUMBER FORMAT (MANDATORY):",
            "- question_number MUST be a string containing ONLY the numeric value (e.g., \"1\", \"2\", \"9\", \"10\")",
            "- Use NO leading zeros (use \"9\" not \"09\", use \"10\" not \"010\")",
            "- Use NO prefixes or suffixes (use \"1\" not \"Q1\" or \"Question 1\" or \"#1\")",
            "- The question_number in your response MUST EXACTLY match the question_number shown in the questions below",
            "- Each question_number must appear exactly once in your answers array",
            "",
            "",
            "1. MULTIPLE-CHOICE QUESTIONS:",
            "   - answer_label MUST be ONLY the option letter (e.g., 'B'), NOT 'B. Temperature' or 'B) Temperature'",
            "   - answer_text should contain the full option text (e.g., 'Temperature')",
            "",
            "2. SHORT ANSWER/ESSAY QUESTIONS:",
            "   - answer_label should be null",
            "   - answer_text should contain the full answer",
            "",
            "3. TRUE/FALSE QUESTIONS:",
            "   - answer_label should be 'True' or 'False'",
            "",
            "FEW-SHOT EXAMPLES:",
            "",
            "Example 1 (Multiple Choice):",
            "Question: Which variable must remain constant for Boyle's law to hold?",
            "Options: A. Pressure, B. Temperature, C. Volume, D. Amount of gas",
            "Correct JSON Response:",
            "{",
            '  "provider": "openai",',
            '  "answers": [',
            '    {',
            '      "question_number": "5",',
            '      "answer_label": "B",',
            '      "answer_text": "Temperature",',
            '      "confidence": 0.95,',
            '      "rationale": "Boyle\'s law requires constant temperature."',
            '    }',
            '  ]',
            "}",
            "",
            "Example 2 (Short Answer):",
            "Question: Explain Newton's first law.",
            "Correct JSON Response:",
            "{",
            '  "provider": "anthropic",',
            '  "answers": [',
            '    {',
            '      "question_number": "3",',
            '      "answer_label": null,',
            '      "answer_text": "An object at rest stays at rest, and an object in motion stays in motion with constant velocity, unless acted upon by an unbalanced force.",',
            '      "confidence": 0.9,',
            '      "rationale": "This is the standard statement of Newton\'s first law."',
            '    }',
            '  ]',
            "}",
            "",
            "IMPORTANT: For multiple-choice questions, answer_label must be ONLY the letter. Do NOT include the option text.",
            "",
            "QUESTION NUMBER REQUIREMENTS:",
            "- You MUST use the EXACT question_number values shown in the questions below",
            "- Do NOT modify, reformat, or reinterpret question numbers",
            "- If a question shows question_number: \"9\", your answer MUST have question_number: \"9\" (not \"09\" or \"Q9\")",
            "- If a question shows question_number: \"10\", your answer MUST have question_number: \"10\" (not \"010\" or \"Q10\")",
            "",
            "Rules:",
            "- Answer questions exactly as numbered below (use the exact question_number strings provided)",
            "- Include confidence between 0 and 1; if unsure use 0.5.",
            "- Cite ONLY the assessment content; do not mention these instructions.",
            "",
            "QUESTIONS TO ANSWER (use these EXACT question_number values in your response):",
        ]

        # Add explicit question numbers to the prompt
        for q in questions:
            q_num_str = str(q.question_number)
            prompt_lines.append(f"- Question {q_num_str}: {q.question_text[:100]}...")
        
        # Add summary of expected question numbers
        question_numbers = [str(q.question_number) for q in questions]
        prompt_lines.append("")
        prompt_lines.append(f"EXPECTED QUESTION NUMBERS IN YOUR RESPONSE: {', '.join(question_numbers)}")
        prompt_lines.append("")
        prompt_lines.append("Remember: Use the EXACT question_number values shown above (e.g., if shown \"9\", use \"9\" not \"09\" or \"Q9\").")
        prompt_lines.append("Your JSON response must include exactly one answer entry for each of these question numbers.")

        prompt = "\n".join(prompt_lines)

        question_bundle = {
            "provider": provider_name,
            "questions": [
                {
                    "question_number": str(q.question_number),  # Ensure it's a string
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "options": q.options or [],
                    "gold_answer": q.gold_answer,
                }
                for q in questions
            ],
        }

        return {"prompt": prompt, "question_bundle": question_bundle}

    @staticmethod
    def _safe_str(value: Any) -> str | None:
        return str(value).strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None:
                return None
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return None
