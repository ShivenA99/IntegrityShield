from __future__ import annotations

import os
import shutil
from pathlib import Path

from werkzeug.datastructures import FileStorage

from ...utils.storage_paths import assets_directory, pdf_input_path, run_directory

# GCP Cloud Storage import (optional - only used if bucket is configured)
try:
    from google.cloud import storage
    CLOUD_STORAGE_AVAILABLE = True
except ImportError:
    CLOUD_STORAGE_AVAILABLE = False


class FileManager:
    def __init__(self):
        """Initialize FileManager with optional Cloud Storage support."""
        self.bucket_name = os.getenv("FAIRTESTAI_FILE_STORAGE_BUCKET")
        self.storage_client = None
        self.bucket = None

        # Only initialize Cloud Storage if bucket is configured and library is available
        if self.bucket_name and CLOUD_STORAGE_AVAILABLE:
            try:
                self.storage_client = storage.Client()
                self.bucket = self.storage_client.bucket(self.bucket_name)
            except Exception as e:
                print(f"Warning: Could not initialize Cloud Storage: {e}")
                self.bucket = None

    def _upload_to_cloud_storage(self, local_path: Path, cloud_path: str) -> None:
        """Upload a file to Cloud Storage (for persistence across container restarts)."""
        if self.bucket:
            try:
                blob = self.bucket.blob(cloud_path)
                blob.upload_from_filename(str(local_path))
            except Exception as e:
                print(f"Warning: Could not upload {cloud_path} to Cloud Storage: {e}")

    def save_uploaded_pdf(self, run_id: str, file: FileStorage) -> Path:
        """
        Save uploaded PDF to local storage (for processing) and Cloud Storage (for persistence).

        Cloud Run containers are ephemeral, so we store files in both:
        - Local /tmp: For immediate processing during pipeline run
        - Cloud Storage: For long-term persistence and retrieval
        """
        filename = file.filename or "uploaded.pdf"
        destination = pdf_input_path(run_id, filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        file.save(destination)

        # Also upload to Cloud Storage if configured
        if self.bucket:
            cloud_path = f"{run_id}/input/{filename}"
            self._upload_to_cloud_storage(destination, cloud_path)

        return destination

    def save_answer_key_pdf(self, run_id: str, file: FileStorage) -> Path:
        """Save answer key PDF to local storage and Cloud Storage."""
        filename = file.filename or "answer_key.pdf"
        destination = pdf_input_path(run_id, f"answer_key_{filename}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        file.save(destination)

        # Also upload to Cloud Storage if configured
        if self.bucket:
            cloud_path = f"{run_id}/input/answer_key_{filename}"
            self._upload_to_cloud_storage(destination, cloud_path)

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
