from __future__ import annotations

from typing import Dict

from .base import AttackHandler
from .code_glyph import CodeGlyphAttack


_REGISTRY: Dict[str, AttackHandler] = {
	"CODE_GLYPH": CodeGlyphAttack(),
}


def get_attack_handler(name: str) -> AttackHandler | None:
	return _REGISTRY.get(name) 