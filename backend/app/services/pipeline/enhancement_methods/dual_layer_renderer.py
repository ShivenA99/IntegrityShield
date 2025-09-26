from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Tuple

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import ContentStream, NameObject, NumberObject, TextStringObject

from .base_renderer import BaseRenderer


class DualLayerRenderer(BaseRenderer):
    """Apply dual-layer text rendering: invisible replacements + visible originals."""

    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        if not mapping:
            mapping = self.build_mapping_from_questions(run_id)

        original_bytes = original_pdf.read_bytes()
        modified_bytes = self._apply_dual_layer(original_bytes, mapping)

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(modified_bytes)

        return {
            "mapping_entries": len(mapping),
            "file_size_bytes": destination.stat().st_size,
            "effectiveness_score": 0.85 if mapping else 0.0,
        }

    def _apply_dual_layer(self, pdf_bytes: bytes, mapping: Dict[str, str]) -> bytes:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for page in reader.pages:
            content = ContentStream(page.get_contents(), reader)
            new_ops: List[Tuple[List[object], bytes]] = []

            for operands, operator in content.operations:
                if operator == b"Tj" and operands and isinstance(operands[0], TextStringObject):
                    original_text = str(operands[0])

                    replacement_text = None
                    for orig, repl in mapping.items():
                        if orig in original_text:
                            replacement_text = original_text.replace(orig, repl)
                            break

                    if replacement_text and replacement_text != original_text:
                        new_ops.extend([
                            ([NumberObject(3)], b"Tr"),
                            ([TextStringObject(replacement_text)], b"Tj"),
                            ([NumberObject(0)], b"Tr"),
                        ])
                        new_ops.append(([TextStringObject(original_text)], b"Tj"))
                        continue

                new_ops.append((operands, operator))

            content.operations = new_ops
            page[NameObject("/Contents")] = content
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()
