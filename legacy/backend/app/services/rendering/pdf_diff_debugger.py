import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None  # type: ignore

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:  # pragma: no cover
    pdfminer_extract_text = None  # type: ignore

logger = logging.getLogger(__name__)


def _extract_with_pymupdf(pdf_path: Path) -> List[str]:
    pages: List[str] = []
    if not fitz:
        logger.warning("[PDF_DIFF] PyMuPDF not available")
        return pages
    try:
        doc = fitz.open(str(pdf_path))
        for i in range(len(doc)):
            page = doc.load_page(i)
            txt = page.get_text("text")  # simple text
            pages.append(txt)
        doc.close()
    except Exception as e:
        logger.error("[PDF_DIFF] PyMuPDF extraction failed: %s", e)
    return pages


def _extract_with_pdfminer(pdf_path: Path) -> str:
    if not pdfminer_extract_text:
        logger.warning("[PDF_DIFF] pdfminer.six not available")
        return ""
    try:
        return pdfminer_extract_text(str(pdf_path))
    except Exception as e:
        logger.error("[PDF_DIFF] pdfminer extraction failed: %s", e)
        return ""


def diff_pdfs(original_pdf: Path, attacked_pdf: Path) -> Dict[str, Any]:
    """
    Extract text from original and attacked PDFs using two different parsers and
    return a structured diff payload. Also log summaries for debugging.
    """
    result: Dict[str, Any] = {
        "original": {
            "pymupdf_pages": [],
            "pdfminer_text": "",
        },
        "attacked": {
            "pymupdf_pages": [],
            "pdfminer_text": "",
        },
        "summary": {},
    }

    logger.info("[PDF_DIFF] Extracting original with PyMuPDF: %s", original_pdf)
    orig_pages = _extract_with_pymupdf(original_pdf)
    logger.info("[PDF_DIFF] Extracting attacked with PyMuPDF: %s", attacked_pdf)
    atk_pages = _extract_with_pymupdf(attacked_pdf)

    result["original"]["pymupdf_pages"] = orig_pages
    result["attacked"]["pymupdf_pages"] = atk_pages

    logger.info("[PDF_DIFF] Extracting original with pdfminer: %s", original_pdf)
    orig_pdfminer = _extract_with_pdfminer(original_pdf)
    logger.info("[PDF_DIFF] Extracting attacked with pdfminer: %s", attacked_pdf)
    atk_pdfminer = _extract_with_pdfminer(attacked_pdf)

    result["original"]["pdfminer_text"] = orig_pdfminer
    result["attacked"]["pdfminer_text"] = atk_pdfminer

    # Build rough summaries
    orig_len = sum(len(p or "") for p in orig_pages)
    atk_len = sum(len(p or "") for p in atk_pages)
    orig_m_len = len(orig_pdfminer or "")
    atk_m_len = len(atk_pdfminer or "")

    summary = {
        "pymupdf": {"original_chars": orig_len, "attacked_chars": atk_len},
        "pdfminer": {"original_chars": orig_m_len, "attacked_chars": atk_m_len},
        "page_count": {"original": len(orig_pages), "attacked": len(atk_pages)},
    }

    result["summary"] = summary

    logger.info("[PDF_DIFF] Summary: %s", summary)

    # Log first 300 chars of each page for quick inspection
    for i, txt in enumerate(orig_pages):
        logger.debug("[PDF_DIFF][ORIG][p%02d] %s", i + 1, (txt or "")[:300])
    for i, txt in enumerate(atk_pages):
        logger.debug("[PDF_DIFF][ATKD][p%02d] %s", i + 1, (txt or "")[:300])

    # Also log first 500 chars of pdfminer outputs
    logger.debug("[PDF_DIFF][ORIG][pdfminer] %s", (orig_pdfminer or "")[:500])
    logger.debug("[PDF_DIFF][ATKD][pdfminer] %s", (atk_pdfminer or "")[:500])

    return result 