from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz

from ...utils.time import isoformat, utc_now


@dataclass
class ManualQuestion:
    number: int
    section_label: str
    stem_text: str
    question_type: str
    options: Dict[str, str]
    gold_answer: Optional[str]
    marks: Optional[int]
    explanation: Optional[str]
    source_dataset: Optional[str]
    source_id: Optional[str]


@dataclass
class ManualRunPayload:
    pdf_path: Path
    page_count: int
    questions: List[ManualQuestion]
    structured_data: Dict[str, Any]


class ManualInputLoader:
    def __init__(self, manual_dir: Path) -> None:
        self.manual_dir = manual_dir

    def build(self) -> ManualRunPayload:
        if not self.manual_dir.exists():
            raise FileNotFoundError(f"Manual input directory not found: {self.manual_dir}")

        pdf_path = self._find_single_file(".pdf")
        tex_path = self._find_single_file(".tex")
        gold_path = self._find_optional_file("_gold.json")

        page_count = self._resolve_page_count(pdf_path)
        tex_content = tex_path.read_text(encoding="utf-8")

        if gold_path:
            metadata, questions = self._load_from_legacy_gold(tex_content, gold_path)
        else:
            json_path = self._find_single_file(".json")
            metadata, questions = self._load_from_document_json(tex_content, json_path)

        self._validate_against_tex(tex_content, questions)

        structured = self._build_structured_payload(
            pdf_path=pdf_path,
            page_count=page_count,
            questions=questions,
            doc_meta=metadata,
        )

        return ManualRunPayload(
            pdf_path=pdf_path,
            page_count=page_count,
            questions=questions,
            structured_data=structured,
        )

    def _find_optional_file(self, suffix: str) -> Path | None:
        matches = list(self.manual_dir.glob(f"*{suffix}"))
        if not matches:
            return None
        if len(matches) > 1:
            raise FileExistsError(
                f"Multiple manual input files with suffix '{suffix}' found in {self.manual_dir}"
            )
        return matches[0]

    def _load_from_legacy_gold(self, tex_content: str, gold_path: Path) -> Tuple[Dict[str, Any], List[ManualQuestion]]:
        gold_meta = json.loads(gold_path.read_text(encoding="utf-8"))
        mcq_answers, tf_answers = self._split_gold_answers(gold_meta.get("answers", []))

        mcq_questions = self._parse_mcq_questions(tex_content)
        tf_questions = self._parse_tf_questions(tex_content)

        if len(mcq_questions) != len(mcq_answers):
            raise ValueError(
                f"Mismatch between MCQ questions ({len(mcq_questions)}) and gold answers ({len(mcq_answers)})"
            )
        if len(tf_questions) != len(tf_answers):
            raise ValueError(
                f"Mismatch between True/False questions ({len(tf_questions)}) and gold answers ({len(tf_answers)})"
            )

        questions: List[ManualQuestion] = []

        absolute_index = 1
        for idx, entry in enumerate(mcq_questions):
            gold_entry = mcq_answers[idx]
            questions.append(
                ManualQuestion(
                    number=absolute_index,
                    section_label="Multiple Choice",
                    stem_text=entry["stem"],
                    question_type="mcq_single",
                    options=entry["options"],
                    gold_answer=(gold_entry.get("correct_answer") or "").strip() or None,
                    marks=self._safe_int(gold_entry.get("marks")),
                    explanation=self._clean_optional_text(gold_entry.get("explanation")),
                    source_dataset=gold_entry.get("source_dataset"),
                    source_id=gold_entry.get("source_id"),
                )
            )
            absolute_index += 1

        for idx, entry in enumerate(tf_questions):
            gold_entry = tf_answers[idx]
            questions.append(
                ManualQuestion(
                    number=absolute_index,
                    section_label="True / False",
                    stem_text=entry,
                    question_type="true_false",
                    options={"True": "True", "False": "False"},
                    gold_answer=(gold_entry.get("correct_answer") or "").strip() or None,
                    marks=self._safe_int(gold_entry.get("marks")),
                    explanation=self._clean_optional_text(gold_entry.get("explanation")),
                    source_dataset=gold_entry.get("source_dataset"),
                    source_id=gold_entry.get("source_id"),
                )
            )
            absolute_index += 1

        return gold_meta, questions

    def _load_from_document_json(
        self, tex_content: str, json_path: Path
    ) -> Tuple[Dict[str, Any], List[ManualQuestion]]:
        doc_meta = json.loads(json_path.read_text(encoding="utf-8"))
        question_entries = doc_meta.get("questions") or []
        if not question_entries:
            raise ValueError("Manual input JSON missing 'questions' array")

        questions: List[ManualQuestion] = []

        for idx, entry in enumerate(question_entries):
            number = self._safe_int(entry.get("question_number")) or idx + 1
            question_type_raw = (entry.get("question_type") or "").strip().lower()
            question_type, section_label = self._map_question_type(question_type_raw)

            stem_text = self._clean_optional_text(entry.get("stem_text")) or ""
            options = self._normalize_options(entry.get("options") or {}, question_type)
            gold_answer = self._clean_optional_text(entry.get("gold_answer"))
            marks = self._safe_int(entry.get("marks"))
            explanation = self._clean_optional_text(entry.get("answer_explanation"))

            source_info = entry.get("source") or {}
            source_dataset = source_info.get("dataset")
            source_id = source_info.get("source_id")

            questions.append(
                ManualQuestion(
                    number=number,
                    section_label=section_label,
                    stem_text=stem_text,
                    question_type=question_type,
                    options=options,
                    gold_answer=gold_answer,
                    marks=marks,
                    explanation=explanation,
                    source_dataset=source_dataset,
                    source_id=source_id,
                )
            )

        return doc_meta, sorted(questions, key=lambda q: q.number)

    def _validate_against_tex(self, tex_content: str, questions: List[ManualQuestion]) -> None:
        mcq_questions = [q for q in questions if q.question_type.startswith("mcq")]
        tf_questions = [q for q in questions if q.question_type.startswith("true")]

        try:
            tex_mcq = self._parse_mcq_questions(tex_content)
        except ValueError:
            tex_mcq = []
        try:
            tex_tf = self._parse_tf_questions(tex_content)
        except ValueError:
            tex_tf = []

        if tex_mcq and len(mcq_questions) != len(tex_mcq):
            raise ValueError(
                f"Mismatch between MCQ questions in manual JSON ({len(mcq_questions)}) and TeX file ({len(tex_mcq)})"
            )
        if tex_tf and len(tf_questions) != len(tex_tf):
            raise ValueError(
                f"Mismatch between True/False questions in manual JSON ({len(tf_questions)}) and TeX file ({len(tex_tf)})"
            )

    def _find_single_file(self, suffix: str) -> Path:
        matches = list(self.manual_dir.glob(f"*{suffix}"))
        if not matches:
            raise FileNotFoundError(f"Expected manual input file with suffix '{suffix}' in {self.manual_dir}")
        if len(matches) > 1:
            raise FileExistsError(f"Multiple manual input files with suffix '{suffix}' found in {self.manual_dir}")
        return matches[0]

    def _resolve_page_count(self, pdf_path: Path) -> int:
        doc = fitz.open(pdf_path)
        try:
            return int(doc.page_count)
        finally:
            doc.close()

    def _split_gold_answers(self, answers: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        mcq, tf = [], []
        for entry in answers:
            if (entry.get("type") or "").lower() == "mcq":
                mcq.append(entry)
            elif (entry.get("type") or "").lower() in {"tf", "true_false"}:
                tf.append(entry)
        return mcq, tf

    def _parse_mcq_questions(self, tex_content: str) -> List[Dict[str, Any]]:
        section_match = re.search(
            r"\\section\*\{Multiple Choice[\s\S]*?\\section\*\{True / False",
            tex_content,
        )
        if not section_match:
            raise ValueError("Unable to locate Multiple Choice section in manual TeX file")
        section_text = section_match.group(0)

        pattern = re.compile(
            r"\\item\s+(.*?)\\begin\{enumerate\}\[label=\(\\alph\*\)\](.*?)\\end\{enumerate\}",
            re.S,
        )

        questions: List[Dict[str, Any]] = []
        for match in pattern.finditer(section_text):
            stem_raw = match.group(1)
            options_block = match.group(2)
            stem_text = self._clean_tex_text(stem_raw)
            options = self._parse_options(options_block)
            questions.append({"stem": stem_text, "options": options})

        return questions

    def _parse_tf_questions(self, tex_content: str) -> List[str]:
        section_match = re.search(
            r"\\section\*\{True / False[\s\S]*?\\end\{document\}",
            tex_content,
        )
        if not section_match:
            raise ValueError("Unable to locate True / False section in manual TeX file")
        section_text = section_match.group(0)

        tf_pattern = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{enumerate\})", re.S)
        questions: List[str] = []
        for match in tf_pattern.finditer(section_text):
            stem = self._clean_tex_text(match.group(1))
            if stem:
                questions.append(stem)
        return questions

    def _parse_options(self, block: str) -> Dict[str, str]:
        labels = [chr(ord("A") + idx) for idx in range(26)]
        parts = re.split(r"\\item\s+", block)
        options: Dict[str, str] = {}
        for idx, raw_part in enumerate(parts[1:]):
            label = labels[idx] if idx < len(labels) else str(idx + 1)
            truncated = raw_part.split("\\end{enumerate}", 1)[0]
            value = self._clean_tex_text(truncated)
            if value:
                options[label] = value
        return options

    def _clean_tex_text(self, value: str) -> str:
        cleaned = value
        cleaned = re.sub(r"\\textit\{([^}]*)\}", r"\1", cleaned)
        cleaned = cleaned.replace("\\n", " ")
        cleaned = cleaned.replace("\\", " ")
        cleaned = cleaned.replace("{", "")
        cleaned = cleaned.replace("}", "")
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _map_question_type(self, question_type: str) -> Tuple[str, str]:
        qtype = question_type.lower()
        if qtype in {"mcq", "multiple_choice", "mcq_single"}:
            return "mcq_single", "Multiple Choice"
        if qtype in {"tf", "true_false", "true/false", "true-false"}:
            return "true_false", "True / False"
        # Default fallback for unsupported types
        return (qtype or "unknown", question_type or "Question")

    def _normalize_options(self, options: Dict[str, Any], question_type: str) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        if not isinstance(options, dict):
            options = {}

        for key, value in options.items():
            label = str(key).strip()
            text = self._clean_optional_text(value)
            if not label or not text:
                continue
            if question_type == "mcq_single":
                label = label.upper()
            normalized[label] = text

        if not normalized and question_type == "true_false":
            normalized = {"True": "True", "False": "False"}

        return normalized

    def _clean_optional_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _safe_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _build_structured_payload(
        self,
        *,
        pdf_path: Path,
        page_count: int,
        questions: List[ManualQuestion],
        doc_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        ai_questions: List[Dict[str, Any]] = []
        question_index: List[Dict[str, Any]] = []

        for question in questions:
            q_number = str(question.number)
            options_payload = {key: value for key, value in (question.options or {}).items()}
            ai_entry = {
                "question_number": q_number,
                "q_number": q_number,
                "question_type": question.question_type,
                "section_label": question.section_label,
                "stem_text": question.stem_text,
                "options": options_payload,
                "gold_answer": question.gold_answer,
                "metadata": {
                    "marks": question.marks,
                    "explanation": question.explanation,
                    "source_dataset": question.source_dataset,
                    "source_id": question.source_id,
                },
                "positioning": {"page": None},
                "manipulation": {
                    "method": "manual_seed",
                    "substring_mappings": [],
                    "effectiveness_score": None,
                    "auto_generate_status": "prefilled",
                },
            }
            ai_questions.append(ai_entry)

            question_index.append(
                {
                    "q_number": q_number,
                    "page": None,
                    "stem": {"text": question.stem_text, "bbox": None},
                    "options": {key: {"text": value} for key, value in options_payload.items()},
                    "provenance": {"sources_detected": ["manual_input"]},
                }
            )

        structured: Dict[str, Any] = {
            "pipeline_metadata": {
                "run_id": None,
                "current_stage": "smart_reading",
                "stages_completed": ["smart_reading"],
                "total_processing_time_ms": 0,
                "last_updated": isoformat(utc_now()),
                "version": "2.0.0",
                "config": {},
                "manual_input": True,
                "document_id": doc_meta.get("document_id") or doc_meta.get("docid"),
                "domain": doc_meta.get("domain"),
                "academic_level": doc_meta.get("academic_level"),
            },
            "document": {
                "source_path": str(pdf_path),
                "filename": pdf_path.name,
                "pages": page_count,
            },
            "ai_extraction": {
                "source": "manual_input",
                "confidence": 1.0,
                "questions_found": len(questions),
                "processing_time_ms": 0,
                "cost_cents": 0.0,
                "error": None,
                "raw_response": {
                    "orchestration": {
                        "decision_strategy": "manual_seed",
                        "selected_source": "manual_input",
                        "available_sources": ["manual_input"],
                        "total_processing_time_ms": 0,
                        "clients_used": ["manual_input"],
                    }
                },
            },
            "ai_questions": ai_questions,
            "questions": ai_questions.copy(),
            "question_index": question_index,
            "assets": {"images": [], "fonts": [], "extracted_elements": 0},
            "content_elements": [],
            "pymupdf_span_index": [],
            "manual_input": {
                "source_directory": str(self.manual_dir),
                "generated_at": isoformat(utc_now()),
            },
        }

        return structured




