from __future__ import annotations

from pathlib import Path
from typing import Iterable


class BackupService:
    def __init__(self, destination: Path) -> None:
        self.destination = destination
        self.destination.mkdir(parents=True, exist_ok=True)

    def backup_files(self, paths: Iterable[Path]) -> list[Path]:
        copied: list[Path] = []
        for source in paths:
            if source.exists():
                target = self.destination / source.name
                target.write_bytes(source.read_bytes())
                copied.append(target)
        return copied
