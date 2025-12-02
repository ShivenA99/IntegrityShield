from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from ..ai_clients.openai_vision_client import OpenAIVisionClient
from ..ai_clients.mistral_ocr_client import MistralOCRClient
from ..data_management.structured_data_manager import StructuredDataManager


# Optional: paste API keys here for sandbox-only runs (otherwise env vars are used)
# SECURITY: Never commit API keys to version control!
# Set these via environment variables or local .env file instead
OPENAI_API_KEY_OVERRIDE = os.getenv("OPENAI_API_KEY_OVERRIDE") or None
MISTRAL_API_KEY_OVERRIDE = os.getenv("MISTRAL_API_KEY_OVERRIDE") or None





def run_sandbox(pdf_path: Path, run_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"run_id": run_id, "pdf_path": str(pdf_path), "results": {}}

    # Inject overrides into environment if provided
    if OPENAI_API_KEY_OVERRIDE:
        os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY_OVERRIDE
    if MISTRAL_API_KEY_OVERRIDE:
        os.environ["MISTRAL_API_KEY"] = MISTRAL_API_KEY_OVERRIDE

    oai = OpenAIVisionClient()
    mistral = MistralOCRClient()
    sdm = StructuredDataManager()

    base_dir = Path(str(pdf_path)).parent
    raw_dir = base_dir / "raw_sandbox"
    raw_dir.mkdir(exist_ok=True, parents=True)

    if oai.is_configured():
        oai_res = oai.extract_questions_from_pdf(pdf_path, run_id)
        out["results"]["openai_vision"] = {
            "confidence": oai_res.confidence,
            "questions": oai_res.questions,
            "processing_time_ms": oai_res.processing_time_ms,
            "cost_cents": oai_res.cost_cents,
            "error": oai_res.error,
        }
        (raw_dir / "openai_vision.json").write_text(__import__("json").dumps(oai_res.raw_response or {}, indent=2))
    else:
        out["results"]["openai_vision"] = {"error": "OpenAI not configured"}

    if mistral.is_configured():
        mi_res = mistral.extract_questions_from_pdf(pdf_path, run_id)
        out["results"]["mistral_ocr"] = {
            "confidence": mi_res.confidence,
            "questions": mi_res.questions,
            "processing_time_ms": mi_res.processing_time_ms,
            "cost_cents": mi_res.cost_cents,
            "error": mi_res.error,
        }
        (raw_dir / "mistral_ocr.json").write_text(__import__("json").dumps(mi_res.raw_response or {}, indent=2))
    else:
        out["results"]["mistral_ocr"] = {"error": "Mistral not configured"}

    # Persist into structured.json under ai_extraction.sandbox
    try:
        structured = sdm.load(run_id)
        sandbox = structured.setdefault("ai_extraction", {}).setdefault("sandbox", {})
        sandbox.update(out["results"])  # store summaries
        sdm.save(run_id, structured)
    except Exception:
        pass

    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python -m app.services.developer.sandbox_runner <pdf_path> <run_id>")
        sys.exit(1)
    pdf = Path(sys.argv[1])
    rid = sys.argv[2]
    info = run_sandbox(pdf, rid)
    print(__import__("json").dumps(info, indent=2)) 