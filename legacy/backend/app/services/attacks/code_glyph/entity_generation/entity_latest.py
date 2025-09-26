from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def generate_topk_entities_latest(question: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
	try:
		from ....entity_detection.latest_entity_detection.generator import generate_topk_entities_latest as _gen
		opts = _gen(question, top_k=top_k) or []
		logger.info("[LATEST_ENTITY][ADAPTER] Generated %d options", len(opts))
		return opts
	except Exception as e:
		logger.error("[LATEST_ENTITY][ADAPTER] Failed to generate latest entities: %s", e)
		return [] 