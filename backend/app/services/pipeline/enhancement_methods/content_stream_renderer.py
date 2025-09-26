from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import NameObject

from .base_renderer import BaseRenderer


class ContentStreamRenderer(BaseRenderer):
    def render(
        self,
        run_id: str,
        original_pdf: Path,
        destination: Path,
        mapping: Dict[str, str],
    ) -> Dict[str, float | str | int | None]:
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Build mapping from structured data if not provided
        if not mapping:
            mapping = self.build_mapping_from_questions(run_id)

        try:
            reader = PdfReader(str(original_pdf))
            writer = PdfWriter()

            for page in reader.pages:
                content = page.get_contents()
                raw = b""
                if isinstance(content, list):
                    for c in content:
                        raw += c.get_data()
                else:
                    raw = content.get_data() if content else b""

                text = raw.decode("latin-1", errors="ignore")
                replaced = text
                for orig, repl in (mapping or {}).items():
                    if orig:
                        replaced = replaced.replace(orig, repl)

                if replaced != text:
                    from PyPDF2.generic import DecodedStreamObject

                    stream = DecodedStreamObject()
                    stream.set_data(replaced.encode("latin-1", errors="ignore"))
                    page[NameObject("/Contents")] = stream

                writer.add_page(page)

            with destination.open("wb") as f:
                writer.write(f)

            return {
                "mapping_entries": len(mapping),
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": 0.7 if mapping else 0.0,
            }
        except Exception:
            # Fallback to plain copy if manipulation fails
            destination.write_bytes(original_pdf.read_bytes())
            return {
                "mapping_entries": len(mapping),
                "file_size_bytes": destination.stat().st_size,
                "effectiveness_score": 0.0,
            }
