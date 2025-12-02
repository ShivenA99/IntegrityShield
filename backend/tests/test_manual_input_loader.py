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
        "subjects": ["science"],
        "combination_used": ["science_combo"],
        "total_marks": 5,
        "number_of_questions": 3,
        "number_of_pages": 1,
        "generated_at": "2025-01-01",
        "version": "1.0",
        "file_paths": {
            "latex_file": "output/science/sample_doc.tex",
            "pdf_file": "output/science/sample_doc.pdf",
        },
        "question_statistics": {
            "by_type": {"MCQ": 2, "TF": 1},
            "by_marks": {"2": 2, "1": 1},
            "total_marks_by_type": {"MCQ": 4, "TF": 1},
        },
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
                "gold_confidence": 0.9,
                "answer_explanation": "Mars is farthest in this list.",
                "has_image": False,
                "image_path": None,
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
                "gold_confidence": 0.8,
                "answer_explanation": "Hydrogen is the lightest element.",
                "has_image": False,
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
                "gold_confidence": 0.95,
                "answer_explanation": "Accepted convention.",
                "has_image": False,
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
    assert payload.doc_metadata["document_name"] == "Sample Document"
    assert payload.source_paths["json"] and payload.source_paths["json"].endswith("sample_doc.json")
    assert payload.source_paths["tex"].endswith("sample_doc.tex")

    first_question = payload.questions[0]
    assert first_question.options["D"] == "Mars"
    assert first_question.question_id == "sample_mcq_1"
    assert first_question.gold_confidence == 0.9

    third_question = payload.questions[2]
    assert third_question.question_type == "true_false"
    assert third_question.options == {"True": "True", "False": "False"}

    structured = payload.structured_data
    assert structured["pipeline_metadata"]["document_id"] == "sample_doc"
    assert structured["pipeline_metadata"]["subjects"] == ["science"]
    assert structured["ai_questions"][0]["options"]["D"] == "Mars"
    assert structured["ai_questions"][0]["question_id"] == "sample_mcq_1"
    assert structured["document"]["latex_path"].endswith("sample_doc.tex")
    assert structured["document"]["source_files"]["latex_file"] == "output/science/sample_doc.tex"
    assert structured["document"]["total_marks"] == 5
    assert structured["questions"] == structured["ai_questions"]
    assert structured["manual_input"]["source_directory"] == str(manual_dir)
    assert structured["manual_input"]["json_path"].endswith("sample_doc.json")
    assert structured["question_index"][0]["question_id"] == "sample_mcq_1"
    assert structured["question_statistics"]["by_type"] == {"MCQ": 2, "TF": 1}

