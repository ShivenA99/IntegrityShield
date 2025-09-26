from __future__ import annotations

from pathlib import Path


class LegacyAdapter:
    def __init__(self, legacy_root: Path | None = None) -> None:
        self.legacy_root = legacy_root or Path.cwd() / "legacy"

    def has_legacy_system(self) -> bool:
        return self.legacy_root.exists()
