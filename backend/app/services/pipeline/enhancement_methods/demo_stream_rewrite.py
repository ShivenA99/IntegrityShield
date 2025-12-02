from __future__ import annotations

"""Simple proof-of-concept stream rewriting utility.

This helper bypasses the geometry-driven matching logic used by
``ContentStreamRenderer`` and instead performs a direct search-and-replace on
individual ``Tj`` and ``TJ`` operations. The goal is to demonstrate that the PDF
content streams can be modified in-place without involving the full
deterministic matching pipeline.

The implementation intentionally keeps the supported surface area small:

* Only literal strings contained within a single ``Tj`` or ``TJ`` operator are
  eligible for replacement.
* Replacement is global within the operator text (``str.replace`` semantics).
* Font encodings and glyph metrics are not adjusted; this is acceptable for
  proof-of-concept scenarios where the replacement text is comparable in
  length.

Two entry points are provided:

``rewrite_words_in_memory``
    Accepts PDF bytes and a mapping of original → replacement text, returning a
    new PDF byte string.

``rewrite_words_to_file``
    Convenience wrapper that reads from ``Path`` objects and writes the updated
    document back to disk.

These helpers live separately from the production renderer so they can be used
for experiments, smoke tests, or demos without disturbing the main pipeline.
"""

from pathlib import Path
from typing import Dict, Iterable, Tuple
import io

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    ArrayObject,
    ByteStringObject,
    ContentStream,
    NameObject,
    TextStringObject,
)


DEFAULT_REPLACEMENTS: Dict[str, str] = {
    "FairTestAI": "FairTestDemo",
    "assessment": "evaluation",
    "simulator": "prototype",
}


class DemoStreamRewriter:
    """Utility with minimal helpers to rewrite content-stream text."""

    @staticmethod
    def rewrite_words_in_memory(pdf_bytes: bytes, replacements: Dict[str, str]) -> bytes:
        """Return a PDF with direct string replacements applied.

        Parameters
        ----------
        pdf_bytes:
            Original PDF content.
        replacements:
            Mapping of substrings to replace. Each occurrence inside individual
            ``Tj``/``TJ`` operators is rewritten using ``str.replace``.
        """

        if not pdf_bytes:
            return pdf_bytes

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        normalized_pairs = DemoStreamRewriter._normalize_pairs(replacements.items())
        if not normalized_pairs:
            for page in reader.pages:
                writer.add_page(page)
        else:
            for page in reader.pages:
                content = ContentStream(page.get_contents(), reader)
                new_operations: list[Tuple[Iterable, bytes]] = []
                page_modified = False

                for operands, operator in content.operations:
                    if operator == b"Tj" and operands:
                        text_obj = operands[0]
                        decoded = DemoStreamRewriter._decode(text_obj)
                        replaced = DemoStreamRewriter._apply(decoded, normalized_pairs)
                        if replaced != decoded:
                            operands = [TextStringObject(replaced)]
                            page_modified = True
                    elif operator == b"TJ" and operands:
                        array_obj = operands[0]
                        if isinstance(array_obj, ArrayObject):
                            new_array = ArrayObject()
                            segment_modified = False
                            for item in array_obj:
                                if isinstance(item, (TextStringObject, ByteStringObject)):
                                    decoded = DemoStreamRewriter._decode(item)
                                    replaced = DemoStreamRewriter._apply(decoded, normalized_pairs)
                                    if replaced != decoded:
                                        segment_modified = True
                                        new_array.append(TextStringObject(replaced))
                                    else:
                                        new_array.append(item)
                                else:
                                    new_array.append(item)
                            if segment_modified:
                                operands = [new_array]
                                page_modified = True
                    new_operations.append((operands, operator))

                if page_modified:
                    content.operations = new_operations
                    page[NameObject("/Contents")] = content
                writer.add_page(page)

        buffer = io.BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    @staticmethod
    def rewrite_words_to_file(
        source: Path,
        destination: Path,
        replacements: Dict[str, str] | None = None,
    ) -> Path:
        """Rewrite a few words in ``source`` and persist the result to ``destination``."""

        pdf_bytes = source.read_bytes()
        active_replacements = replacements or DEFAULT_REPLACEMENTS
        updated = DemoStreamRewriter.rewrite_words_in_memory(pdf_bytes, active_replacements)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(updated)
        return destination

    @staticmethod
    def _normalize_pairs(pairs: Iterable[Tuple[str, str]]) -> Tuple[Tuple[str, str], ...]:
        normalized: list[Tuple[str, str]] = []
        for original, replacement in pairs:
            if not original:
                continue
            if replacement is None:
                continue
            normalized.append((str(original), str(replacement)))
        return tuple(normalized)

    @staticmethod
    def _decode(text_obj: object) -> str:
        if isinstance(text_obj, TextStringObject):
            return str(text_obj)
        if isinstance(text_obj, ByteStringObject):
            data = bytes(text_obj)
            for encoding in ("utf-8", "latin-1", "utf-16-be"):
                try:
                    return data.decode(encoding)
                except Exception:
                    continue
        return ""

    @staticmethod
    def _apply(text: str, replacements: Tuple[Tuple[str, str], ...]) -> str:
        updated = text
        for original, replacement in replacements:
            if original and original in updated:
                updated = updated.replace(original, replacement)
        return updated


__all__ = ["DemoStreamRewriter"]
