from __future__ import annotations

from pathlib import Path
from typing import Dict, Any


def diff_pdfs(original_pdf: Path, attacked_pdf: Path) -> Dict[str, Any]:
	"""Lightweight PDF diff stub.
	
	Returns a minimal summary to satisfy optional debugging calls without raising.
	"""
	try:
		return {
			"summary": f"pdf-diff disabled (orig={original_pdf.name}, attacked={attacked_pdf.name})",
			"supported": False,
		}
	except Exception:
		return {"summary": "pdf-diff failed", "supported": False} 