from __future__ import annotations

import json
from unittest.mock import patch

from app import create_app
from app.extensions import db
from app.models import QuestionManipulation
from app.services.data_management.structured_data_manager import StructuredDataManager
from app.services.pipeline.latex_dual_layer_service import (
    CompilePass,
    CompileSummary,
    LatexAttackService,
    OverlaySummary,
)
from app.utils.storage_paths import artifacts_root, enhanced_pdf_path


def test_latex_attack_service_generates_artifacts(tmp_path):
    app = create_app("testing")
    app.config["PIPELINE_STORAGE_ROOT"] = tmp_path / "runs"

    with app.app_context():
        db.create_all()

        run_id = "run-test"
        manual_dir = tmp_path / "manual"
        manual_dir.mkdir()

        tex_path = manual_dir / "doc.tex"
        tex_path.write_text(
            r"""
            \documentclass{article}
            \begin{document}
            Mercury is the smallest planet.
            \end{document}
            """,
            encoding="utf-8",
        )

        pdf_path = manual_dir / "doc.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n%EOF")

        structured = {
            "document": {
                "source_path": str(pdf_path),
                "latex_path": str(tex_path),
            },
            "manual_input": {
                "tex_path": str(tex_path),
                "pdf_path": str(pdf_path),
            },
            "pipeline_metadata": {},
        }

        StructuredDataManager().save(run_id, structured)

        question = QuestionManipulation(
            pipeline_run_id=run_id,
            question_number="1",
            question_type="mcq_single",
            original_text="Mercury is the smallest planet.",
            options_data={"A": "Mercury", "B": "Mars"},
            substring_mappings=[
                {
                    "id": "map-1",
                    "original": "Mercury",
                    "replacement": "Mars",
                }
            ],
            ai_model_results={
                "manual_seed": {
                    "question_id": "q1",
                }
            },
        )

        db.session.add(question)
        db.session.commit()

        service = LatexAttackService()

        artifacts_dir = artifacts_root(run_id) / "latex-dual-layer"

        def fake_compile(tex_source_path, mutated_tex_path, output_pdf_path, log_path):
            output_pdf_path.write_bytes(b"%PDF-1.4\n%%mock compiled\n%EOF")
            log_path.write_text("pdflatex log", encoding="utf-8")
            return CompileSummary(
                success=True,
                duration_ms=12.5,
                passes=[CompilePass(number=1, return_code=0, duration_ms=6.0, log_length=10)],
                error=None,
            )

        def fake_overlay(original_pdf_path, compiled_pdf_path, final_pdf_path):
            final_pdf_path.write_bytes(b"%PDF-1.4\n%%mock final\n%EOF")
            return OverlaySummary(
                success=True,
                overlays=1,
                pages_processed=1,
                per_page=[{"page": 1, "overlays": 1}],
            )

        with patch.object(service, "_compile_latex", side_effect=fake_compile), patch.object(
            service, "_overlay_pdfs", side_effect=fake_overlay
        ):
            summary = service.execute(run_id, force=True)

        attacked_tex = artifacts_dir / "latex_dual_layer_attacked.tex"
        assert attacked_tex.exists()
        attacked_content = attacked_tex.read_text(encoding="utf-8")
        assert "\\duallayerbox" in attacked_content

        log_path = artifacts_dir / "latex_dual_layer_log.json"
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        assert payload["replacement_summary"]["replaced"] == 1
        assert payload["replacements"][0]["status"] == "replaced"

        compile_log = artifacts_dir / "latex_dual_layer_compile.log"
        assert compile_log.exists()

        final_pdf = artifacts_dir / "latex_dual_layer_final.pdf"
        assert final_pdf.exists()

        enhanced_pdf = enhanced_pdf_path(run_id, "latex_dual_layer")
        assert enhanced_pdf.exists()

        renderer_metadata = summary["renderer_metadata"]
        assert renderer_metadata["replacements"] == 1
        assert renderer_metadata["overlay_applied"] == 1

        db.session.remove()
        db.drop_all()

