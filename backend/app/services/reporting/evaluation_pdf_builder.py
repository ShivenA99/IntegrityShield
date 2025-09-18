from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)


class EvaluationPdfBuilder:
    """Render an evaluation PDF summarizing results and per-question outcomes."""

    def __init__(self, output_path: Path):
        self.output_path = Path(output_path)
        self.page_width, self.page_height = letter
        self.margin = 40
        self.content_width = self.page_width - 2 * self.margin

    def build(self, attack_mode: str, questions: List[Dict[str, Any]], evaluation: Dict[str, Any]) -> Path:
        c = canvas.Canvas(str(self.output_path), pagesize=letter)
        try:
            self._draw_cover(c, attack_mode, evaluation)
            self._draw_overall_stats(c, evaluation)
            self._draw_per_q_table(c, attack_mode, questions, evaluation)
            c.save()
            logger.info("[EVAL_PDF] Evaluation PDF saved: %s", self.output_path)
            return self.output_path
        except Exception as e:
            logger.error("[EVAL_PDF] Failed to render evaluation PDF: %s", e)
            c.save()
            return self.output_path

    def _draw_cover(self, c: canvas.Canvas, attack_mode: str, evaluation: Dict[str, Any]) -> None:
        c.setTitle("Assessment Evaluation Report")
        c.setFont("Helvetica-Bold", 20)
        c.drawString(self.margin, self.page_height - 100, "Assessment Evaluation Report")
        c.setFont("Helvetica", 12)
        c.drawString(self.margin, self.page_height - 125, f"Attack Mode: {attack_mode.title()}")
        rate = evaluation.get("success_rate") or (evaluation.get("attack_success_summary", {}).get("overall", {}).get("rate"))
        if rate is not None:
            c.drawString(self.margin, self.page_height - 145, f"Overall Attack Success Rate: {float(rate):.1f}%")
        c.showPage()

    def _draw_overall_stats(self, c: canvas.Canvas, evaluation: Dict[str, Any]) -> None:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(self.margin, self.page_height - 60, "Overall Statistics")
        c.setFont("Helvetica", 10)
        y = self.page_height - 80
        # By question type if available
        by_qt = (evaluation.get("attack_success_summary") or {}).get("by_question_type") or {}
        if by_qt:
            for qtype, stats in by_qt.items():
                c.drawString(self.margin, y, f"{qtype}: {stats.get('rate', 0):.1f}% ({stats.get('successful', 0)}/{stats.get('total', 0)})")
                y -= 16
        else:
            c.drawString(self.margin, y, "No per-question-type statistics available.")
            y -= 16
        c.showPage()

    def _draw_per_q_table(self, c: canvas.Canvas, attack_mode: str, questions: List[Dict[str, Any]], evaluation: Dict[str, Any]) -> None:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(self.margin, self.page_height - 60, "Per-Question Results")
        c.setFont("Helvetica", 9)
        y = self.page_height - 85
        col_w = [60, 90, 90, self.content_width - 60 - 90 - 90]
        # Header
        headers = ["Q#", "Gold (OpenAI)", "Attacked AI", "Attack Success"]
        self._row(c, y, col_w, headers, header=True)
        y -= 18
        per_q = evaluation.get("per_question") or {}
        # Normalize per_q keys to str
        per_q = {str(k): v for k, v in per_q.items()}
        for q in questions:
            qn = str(q.get("q_number"))
            row = per_q.get(qn, {})
            gold = q.get("gold_answer", "")
            attacked_ans = row.get("ai_answer") or row.get("predicted_label") or "UNKNOWN"
            # success semantics
            if attack_mode == "detection":
                success = row.get("targeted_hit") or row.get("attack_success") or False
            else:
                success = row.get("prevention_success") or row.get("attack_success") or False
            self._row(c, y, col_w, [qn, str(gold)[:24], str(attacked_ans)[:24], "YES" if success else "NO"]) 
            y -= 16
            if y < 80:
                c.showPage()
                c.setFont("Helvetica-Bold", 14)
                c.drawString(self.margin, self.page_height - 60, "Per-Question Results (cont.)")
                c.setFont("Helvetica", 9)
                y = self.page_height - 85
                self._row(c, y, col_w, headers, header=True)
                y -= 18
        c.showPage()

    def _row(self, c: canvas.Canvas, y: float, col_w: List[int], cells: List[str], header: bool = False) -> None:
        x = self.margin
        if header:
            c.setFillColor(Color(0.85, 0.9, 0.95))
            c.rect(x, y - 14, self.content_width, 16, fill=1, stroke=0)
            c.setFillColor(Color(0.2, 0.2, 0.4))
        else:
            c.setFillColor(Color(0, 0, 0))
        c.setFont("Helvetica-Bold" if header else "Helvetica", 9 if header else 8)
        for i, text in enumerate(cells):
            c.drawString(x + 4, y - (2 if header else 0), str(text))
            x += col_w[i] 