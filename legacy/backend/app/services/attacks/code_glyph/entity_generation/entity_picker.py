from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class PickerConfig:
    allow_formatted: bool = False
    prefer_numeric: bool = True
    prefer_negation: bool = True
    min_token_len: int = 2


_NEGATIONS = {"not", "never", "no", "none", "except", "least"}
_STOPWORDS = {"the", "a", "an", "is", "are", "to", "of", "in", "on", "and", "or", "for", "by", "with", "at"}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9]+", text or "")


def _is_numeric(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+", tok))


def _pick_output_variant(input_tok: str) -> str:
    # Simple output variants: numeric +-1; word-level near confounders
    if _is_numeric(input_tok):
        try:
            n = int(input_tok)
            if n >= 10:
                return str(n + 1)
            return str(n + 1)
        except Exception:
            return input_tok
    # Simple letter substitution to preserve width in Latin
    if len(input_tok) == 1:
        swaps = {"i": "l", "l": "i", "o": "a", "a": "o", "e": "g", "m": "rn", "n": "m"}
        return swaps.get(input_tok.lower(), input_tok)
    # Prefer a slight internal letter change
    if len(input_tok) >= 3:
        return input_tok[:-1] + ("o" if input_tok[-1].lower() != "o" else "a")
    return input_tok


def _span_is_formatted(span: Dict[str, Any]) -> bool:
    # PyMuPDF span dict often has 'flags' bitmask; 1=bold, 2=italic in many cases.
    try:
        flags = int(span.get("flags", 0))
        return bool(flags & 0x3)
    except Exception:
        return False


def _find_spans_in_bbox(page: fitz.Page, bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
    x0, y0, x1, y1 = bbox
    textdict = page.get_text("dict", clip=fitz.Rect(x0, y0, x1, y1))
    spans: List[Dict[str, Any]] = []
    for block in textdict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                spans.append(span)
    return spans


def _span_tokens(span: Dict[str, Any]) -> List[str]:
    return _tokenize(span.get("text", ""))


def pick_entities_for_question(question: Dict[str, Any], ocr_doc: Dict[str, Any] | None, config: PickerConfig) -> Dict[str, Any]:
    stem_text = question.get("stem_text") or ""
    tokens = _tokenize(stem_text)
    if not tokens:
        return {"entities": {"input_entity": "A", "output_entity": "B"}, "rationale": "No tokens found; fallback."}

    # Build uniqueness counts
    counts: Dict[str, int] = {}
    for t in tokens:
        tl = t.lower()
        counts[tl] = counts.get(tl, 0) + 1

    # Locate stem bbox/page via context_ids
    pages = (ocr_doc or {}).get("document", {}).get("pages", []) if ocr_doc else []
    page_index: Optional[int] = None
    stem_bbox: Optional[Tuple[float, float, float, float]] = None
    if question.get("context_ids") and pages:
        id_to_item: Dict[str, Dict[str, Any]] = {}
        for p in pages:
            for it in p.get("items", []) or []:
                id_to_item[it.get("id")] = it
        for cid in question.get("context_ids") or []:
            it = id_to_item.get(cid)
            if it and it.get("type") == "text_block":
                try:
                    bbox = tuple(float(v) for v in it.get("bbox", []))
                    stem_bbox = (bbox[0], bbox[1], bbox[2], bbox[3])
                    page_index = int(p.get("page_index", 0)) if (p := next((pg for pg in pages if it in pg.get("items", [])), None)) else 0
                    break
                except Exception:
                    continue

    formatted_tokens: set[str] = set()
    if page_index is not None and stem_bbox is not None and ocr_doc and (src := (ocr_doc.get("document", {}) or {}).get("source_path")):
        try:
            doc = fitz.open(str(src))
            page = doc.load_page(int(page_index))
            spans = _find_spans_in_bbox(page, stem_bbox)
            for sp in spans:
                if _span_is_formatted(sp):
                    for tok in _span_tokens(sp):
                        formatted_tokens.add(tok.lower())
            doc.close()
        except Exception as e:
            logger.debug("[entity_picker] Could not read span formatting: %s", e)

    # Build candidates list with scores
    candidates: List[Tuple[float, str]] = []
    for t in tokens:
        tl = t.lower()
        if len(t) < config.min_token_len:
            continue
        if tl in _STOPWORDS:
            continue
        if counts.get(tl, 0) != 1:
            continue
        if not config.allow_formatted and tl in formatted_tokens:
            continue
        score = 0.0
        if config.prefer_numeric and _is_numeric(t):
            score += 3.0
        if config.prefer_negation and tl in _NEGATIONS:
            score += 2.0
        # Rarity: shorter frequency better here (unique already), add small bonus for length
        score += min(len(t) / 10.0, 1.0)
        candidates.append((score, t))

    candidates.sort(key=lambda p: (-p[0], p[1]))

    chosen_in: Optional[str] = None
    for _score, tok in candidates:
        chosen_in = tok
        break

    if not chosen_in:
        # Fallback to first unique token
        for t in tokens:
            if counts.get(t.lower(), 0) == 1:
                chosen_in = t
                break
    if not chosen_in:
        chosen_in = tokens[0]

    chosen_out = _pick_output_variant(chosen_in)

    rationale = {
        "unique": True,
        "formatted": (chosen_in.lower() in formatted_tokens),
        "prefer_numeric": _is_numeric(chosen_in),
        "chosen_in": chosen_in,
        "chosen_out": chosen_out,
    }
    return {"entities": {"input_entity": chosen_in, "output_entity": chosen_out}, "rationale": rationale}


def extract_formatted_tokens(question: Dict[str, Any], ocr_doc: Dict[str, Any] | None) -> List[str]:
    pages = (ocr_doc or {}).get("document", {}).get("pages", []) if ocr_doc else []
    if not pages:
        return []
    # Find stem bbox/page via context_ids
    page_index: Optional[int] = None
    stem_bbox: Optional[Tuple[float, float, float, float]] = None
    id_to_item: Dict[str, Dict[str, Any]] = {}
    for p in pages:
        for it in p.get("items", []) or []:
            id_to_item[it.get("id")] = it
    for cid in question.get("context_ids") or []:
        it = id_to_item.get(cid)
        if it and it.get("type") == "text_block":
            try:
                bbox = tuple(float(v) for v in it.get("bbox", []))
                stem_bbox = (bbox[0], bbox[1], bbox[2], bbox[3])
                page_index = int(p.get("page_index", 0)) if (p := next((pg for pg in pages if it in pg.get("items", [])), None)) else 0
                break
            except Exception:
                continue
    formatted_tokens: set[str] = set()
    src = (ocr_doc.get("document", {}) or {}).get("source_path") if ocr_doc else None
    if page_index is not None and stem_bbox is not None and src:
        try:
            doc = fitz.open(str(src))
            page = doc.load_page(int(page_index))
            spans = _find_spans_in_bbox(page, stem_bbox)
            for sp in spans:
                if _span_is_formatted(sp):
                    for tok in _span_tokens(sp):
                        if tok:
                            formatted_tokens.add(tok)
            doc.close()
        except Exception:
            pass
    return sorted(formatted_tokens) 