from __future__ import annotations

import shutil
from pathlib import Path

from werkzeug.datastructures import FileStorage

from ...utils.storage_paths import assets_directory, pdf_input_path, run_directory


class FileManager:
    def save_uploaded_pdf(self, run_id: str, file: FileStorage) -> Path:
        destination = pdf_input_path(run_id, file.filename or "uploaded.pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)
        file.save(destination)
        return destination

    def import_manual_pdf(self, run_id: str, source_pdf: Path) -> Path:
        if not source_pdf.exists():
            raise FileNotFoundError(f"Manual input PDF not found at {source_pdf}")
        destination = pdf_input_path(run_id, source_pdf.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_pdf, destination)
        return destination

    def delete_run_artifacts(self, run_id: str) -> None:
        directory = run_directory(run_id)
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)

    def store_asset(self, run_id: str, filename: str, data: bytes) -> Path:
        path = assets_directory(run_id) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path
