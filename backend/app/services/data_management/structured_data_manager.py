from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import orjson

from ...utils.storage_paths import structured_data_path
from ...utils.time import isoformat, utc_now


class StructuredDataManager:
    def initialize(self, run_id: str, pdf_path: Path) -> Dict[str, Any]:
        data = {
            "pipeline_metadata": {
                "run_id": run_id,
                "current_stage": "smart_reading",
                "stages_completed": [],
                "total_processing_time_ms": 0,
                "last_updated": isoformat(utc_now()),
                "version": "2.0.0",
                "config": {},
            },
            "document": {
                "source_path": str(pdf_path),
                "filename": pdf_path.name,
            },
            "questions": [],
            "assets": {"images": [], "fonts": []},
            "manipulation_results": {},
            "performance_metrics": {},
        }
        self.save(run_id, data)
        return data

    def load(self, run_id: str) -> Dict[str, Any]:
        path = structured_data_path(run_id)
        if not path.exists():
            return {}
        return orjson.loads(path.read_bytes())

    def save(self, run_id: str, data: Dict[str, Any]) -> None:
        path = structured_data_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))

    def update(self, run_id: str, update: Dict[str, Any]) -> Dict[str, Any]:
        data = self.load(run_id)
        merged = self._deep_merge(data, update)
        self.save(run_id, merged)
        return merged

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in update.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base
