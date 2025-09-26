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
            # Removed separate overall statistics page to keep report concise
            self._draw_per_q_cards(c, attack_mode, questions, evaluation)
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
        # Deprecated in new layout (kept for backward compatibility if needed)
        return

    def _wrap_text(self, c: canvas.Canvas, text: str, max_width: float, font_name: str, font_size: int) -> List[str]:
        text = (text or "").strip()
        if not text:
            return [""]
        words = text.split()
        lines: List[str] = []
        current = ""
        for w in words:
            candidate = (current + (" " if current else "") + w)
            if c.stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                # If single long token doesn't fit, hard-break
                if c.stringWidth(w, font_name, font_size) > max_width:
                    chunk = ""
                    for ch in w:
                        if c.stringWidth(chunk + ch, font_name, font_size) <= max_width:
                            chunk += ch
                        else:
                            lines.append(chunk)
                            chunk = ch
                    current = chunk
                else:
                    current = w
        if current:
            lines.append(current)
        return lines

    def _draw_per_q_cards(self, c: canvas.Canvas, attack_mode: str, questions: List[Dict[str, Any]], evaluation: Dict[str, Any]) -> None:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(self.margin, self.page_height - 60, "Per-Question Results")
        y = self.page_height - 85
        per_q = evaluation.get("per_question") or {}
        per_q = {str(k): v for k, v in per_q.items()}
        for q in questions:
            qn = str(q.get("q_number"))
            row = per_q.get(qn, {})
            gold = q.get("gold_answer") or q.get("gold_answer_full") or ""
            hidden = row.get("expected_wrong") or q.get("wrong_answer") or q.get("wrong_label") or ""
            ai_ans = row.get("ai_answer") or row.get("predicted_label") or "UNKNOWN"
            method = row.get("attack_method") or q.get("attack_method") or (attack_mode if attack_mode in {"detection", "prevention"} else "unknown")
            if attack_mode == "detection":
                success = bool(row.get("targeted_hit") or row.get("attack_success"))
            else:
                success = bool(row.get("prevention_success") or row.get("attack_success"))

            # Card layout box
            c.setFont("Helvetica", 10)
            lines = []
            lines.append([("Q#", qn)])
            lines.append([("Gold", str(gold))])
            lines.append([("Hidden", str(hidden))])
            lines.append([("Model", str(ai_ans))])
            lines.append([("Method", str(method))])
            lines.append([("Success", "YES" if success else "NO")])

            # Compute card height with wrapped content
            max_label_w = 70
            value_w = self.content_width - max_label_w - 16
            wrapped_rows: List[List[str]] = []
            for (label, value) in [(k, v) for row in lines for (k, v) in row]:
                wrapped = self._wrap_text(c, value, value_w, "Helvetica", 10)
                wrapped_rows.append([label] + wrapped)
            card_lines = sum(len(r) - 0 for r in wrapped_rows)
            card_height = 18 + card_lines * 12 + 8

            if y - card_height < 60:
                c.showPage()
                c.setFont("Helvetica-Bold", 14)
                c.drawString(self.margin, self.page_height - 60, "Per-Question Results (cont.)")
                y = self.page_height - 85

            # Draw card background
            c.setFillColor(Color(0.96, 0.97, 0.99))
            c.rect(self.margin, y - card_height + 6, self.content_width, card_height, fill=1, stroke=0)
            c.setFillColor(Color(0.2, 0.2, 0.2))
            c.setFont("Helvetica", 10)

            # Render rows
            row_y = y - 20
            for (label, value) in [(k, v) for row in lines for (k, v) in row]:
                # label
                c.setFont("Helvetica-Bold", 10)
                c.drawString(self.margin + 8, row_y, f"{label}:")
                # value
                c.setFont("Helvetica", 10)
                wrapped = self._wrap_text(c, value, value_w, "Helvetica", 10)
                vx = self.margin + 8 + max_label_w
                for i, wline in enumerate(wrapped):
                    c.drawString(vx, row_y - 12 * i, wline)
                row_y -= max(12 * max(1, len(wrapped)), 14)

            y -= card_height + 8

        c.showPage() 