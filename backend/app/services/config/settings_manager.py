from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Dict


class SettingsManager:
    """Persist and retrieve global configuration for PDF rendering tweaks."""

    DEFAULTS: Dict[str, float] = {
        "suffix_spacing_bias": 60.0,
    }

    def __init__(self, path: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[3]
        self._path = Path(path) if path else backend_root / "data" / "config" / "global_settings.json"
        self._lock = RLock()

    def _ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Dict[str, Any]:
        """Return merged settings with defaults applied."""
        with self._lock:
            if self._path.exists():
                try:
                    with self._path.open("r", encoding="utf-8") as handle:
                        stored = json.load(handle) or {}
                except Exception:
                    stored = {}
            else:
                stored = {}

            merged: Dict[str, Any] = dict(self.DEFAULTS)
            merged.update(stored)
            return merged

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Persist provided updates and return the merged settings."""
        with self._lock:
            current = {}
            if self._path.exists():
                try:
                    with self._path.open("r", encoding="utf-8") as handle:
                        current = json.load(handle) or {}
                except Exception:
                    current = {}

            for key, value in updates.items():
                if key in self.DEFAULTS:
                    try:
                        current[key] = float(value)
                    except (TypeError, ValueError):
                        continue

            self._ensure_parent()
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(current, handle, indent=2)

            merged: Dict[str, Any] = dict(self.DEFAULTS)
            merged.update(current)
            return merged

    def get_suffix_spacing_bias(self) -> float:
        settings = self.load()
        value = settings.get("suffix_spacing_bias", self.DEFAULTS["suffix_spacing_bias"])
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(self.DEFAULTS["suffix_spacing_bias"])
