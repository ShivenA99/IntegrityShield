from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def ensure_metrics_cache(cache_dir: Path) -> Dict[str, Any]:
	cache_dir.mkdir(parents=True, exist_ok=True)
	logger.info("[NEW_RENDER][METRICS] Using placeholder metrics cache at %s", cache_dir)
	return {"ok": True} 