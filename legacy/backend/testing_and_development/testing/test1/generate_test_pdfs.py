#!/usr/bin/env python3
"""Generate a pair of sample PDFs for manual / E2E testing.

Creates:
  * questions.pdf – 5 straightforward MCQ questions
  * answers.pdf   – answer key with one-line rationale

Run this script from the project root:

    python testing/test1/generate_test_pdfs.py

The resulting PDFs will reside in `testing/test1/`.
"""
from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# Questions & Answers definition
# ---------------------------------------------------------------------------
QUESTIONS = [
    {
        "stem": "1. What is the capital of France?",
        "options": ["A) Paris", "B) Lyon", "C) Marseille", "D) Bordeaux"],
        "answer": "A",
        "reason": "Paris is the capital city of France."
    },
    {
        "stem": "2. Which gas do plants primarily absorb for photosynthesis?",
        "options": ["A) Oxygen", "B) Nitrogen", "C) Carbon Dioxide", "D) Hydrogen"],
        "answer": "C",
        "reason": "Plants take in carbon dioxide during photosynthesis."
    },
    {
        "stem": "3. What is 5 × 6?",
        "options": ["A) 11", "B) 30", "C) 56", "D) 60"],
        "answer": "B",
        "reason": "5 multiplied by 6 equals 30."
    },
    {
        "stem": "4. Which planet is known as the Red Planet?",
        "options": ["A) Earth", "B) Mars", "C) Venus", "D) Jupiter"],
        "answer": "B",
        "reason": "Mars appears reddish due to iron oxide on its surface."
    },
    {
        "stem": "5. Who wrote the play 'Romeo and Juliet'?",
        "options": ["A) Charles Dickens", "B) William Shakespeare", "C) Jane Austen", "D) Mark Twain"],
        "answer": "B",
        "reason": "William Shakespeare authored 'Romeo and Juliet'."
    },
]

OUTPUT_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------

def make_questions_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    margin = 1 * inch
    y = height - margin

    c.setTitle("Sample MCQ Questions")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "Sample MCQ Question Paper")
    y -= 0.5 * inch

    c.setFont("Helvetica", 12)
    for q in QUESTIONS:
        c.drawString(margin, y, q["stem"])
        y -= 0.3 * inch
        for opt in q["options"]:
            c.drawString(margin + 0.25 * inch, y, opt)
            y -= 0.25 * inch
        y -= 0.2 * inch  # extra space between questions
        if y < margin:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 12)
    c.save()


def make_answers_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    margin = 1 * inch
    y = height - margin

    c.setTitle("Answer Key")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, y, "Answer Key & Rationale")
    y -= 0.5 * inch

    c.setFont("Helvetica", 12)
    for q in QUESTIONS:
        line = f"{q['stem'].split('.')[0]}. Answer: {q['answer']}  —  {q['reason']}"
        c.drawString(margin, y, line)
        y -= 0.35 * inch
        if y < margin:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 12)
    c.save()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    q_pdf = OUTPUT_DIR / "questions.pdf"
    a_pdf = OUTPUT_DIR / "answers.pdf"

    make_questions_pdf(q_pdf)
    make_answers_pdf(a_pdf)

    print(f"Created {q_pdf.relative_to(Path.cwd())}")
    print(f"Created {a_pdf.relative_to(Path.cwd())}") 