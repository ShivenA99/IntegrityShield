from __future__ import annotations

import json

import fitz

from app.services.pipeline.manual_input_loader import ManualInputLoader


def _create_sample_pdf(path) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text(fitz.Point(72, 72), "Sample Document")
        doc.save(path)
    finally:
        doc.close()


def test_manual_input_loader_reads_combined_json_inputs(tmp_path):
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()

    pdf_path = manual_dir / "sample_doc.pdf"
    _create_sample_pdf(pdf_path)

    tex_content = r"""
    \documentclass{article}
    \begin{document}
    \section*{Multiple Choice}
    \begin{enumerate}[label=\arabic*.]
    \item First MCQ?
    \begin{enumerate}[label=(\alph*)]
        \item Mercury
        \item Venus
        \item Earth
        \item Mars
    \end{enumerate}
    \item Second MCQ?
    \begin{enumerate}[label=(\alph*)]
        \item Hydrogen
        \item Helium
        \item Carbon
        \item Oxygen
    \end{enumerate}
    \end{enumerate}

    \section*{True / False}
    \begin{enumerate}[label=\arabic*.]
    \item The Sun rises in the east.
    \end{enumerate}
    \end{document}
    """
    (manual_dir / "sample_doc.tex").write_text(tex_content, encoding="utf-8")

    json_payload = {
        "docid": "sample_doc",
        "document_name": "Sample Document",
        "domain": "science",
        "academic_level": "K-12",
        "questions": [
            {
                "question_number": 1,
                "question_id": "sample_mcq_1",
                "question_type": "MCQ",
                "stem_text": "First MCQ?",
                "options": {
                    "A": "Mercury",
                    "B": "Venus",
                    "C": "Earth",
                    "D": "Mars",
                },
                "marks": 2,
                "gold_answer": "D",
                "answer_explanation": "Mars is farthest in this list.",
                "source": {"dataset": "sample_set", "source_id": "q1"},
            },
            {
                "question_number": 2,
                "question_id": "sample_mcq_2",
                "question_type": "mcq",
                "stem_text": "Second MCQ?",
                "options": {
                    "A": "Hydrogen",
                    "B": "Helium",
                    "C": "Carbon",
                    "D": "Oxygen",
                },
                "marks": 2,
                "gold_answer": "A",
                "answer_explanation": "Hydrogen is the lightest element.",
                "source": {"dataset": "sample_set", "source_id": "q2"},
            },
            {
                "question_number": 3,
                "question_id": "sample_tf_1",
                "question_type": "TF",
                "stem_text": "The Sun rises in the east.",
                "options": {"True": "True", "False": "False"},
                "marks": 1,
                "gold_answer": "True",
                "answer_explanation": "Accepted convention.",
                "source": {"dataset": "sample_set", "source_id": "q3"},
            },
        ],
    }
    (manual_dir / "sample_doc.json").write_text(json.dumps(json_payload), encoding="utf-8")

    loader = ManualInputLoader(manual_dir)
    payload = loader.build()

    assert payload.pdf_path.name == "sample_doc.pdf"
    assert payload.page_count == 1
    assert len(payload.questions) == 3

    first_question = payload.questions[0]
    assert first_question.options["D"] == "Mars"

    third_question = payload.questions[2]
    assert third_question.question_type == "true_false"
    assert third_question.options == {"True": "True", "False": "False"}

    structured = payload.structured_data
    assert structured["pipeline_metadata"]["document_id"] == "sample_doc"
    assert structured["ai_questions"][0]["options"]["D"] == "Mars"
    assert structured["questions"] == structured["ai_questions"]
    assert structured["manual_input"]["source_directory"] == str(manual_dir)

