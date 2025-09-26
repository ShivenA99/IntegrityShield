from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ...utils.time import utc_now


class CleanupService:
    def __init__(self, retention_days: int = 7) -> None:
        self.retention = timedelta(days=retention_days)

    def purge_expired_runs(self, root: Path) -> list[str]:
        removed: list[str] = []
        cutoff = utc_now() - self.retention
        if not root.exists():
            return removed

        for run_dir in root.iterdir():
            if not run_dir.is_dir():
                continue
            if run_dir.stat().st_mtime < cutoff.timestamp():
                removed.append(run_dir.name)
                for child in run_dir.glob("*"):
                    if child.is_file():
                        child.unlink(missing_ok=True)
                run_dir.rmdir()
        return removed
