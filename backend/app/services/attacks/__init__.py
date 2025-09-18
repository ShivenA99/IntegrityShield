from __future__ import annotations

from typing import Dict, Callable, Optional

from .base import AttackHandler

# Lazy factory registry to avoid circular imports
_REGISTRY_FACTORY: Dict[str, Callable[[], AttackHandler]] = {}
_REGISTRY: Dict[str, AttackHandler] = {}


def _register_defaults() -> None:
	# Register Code Glyph lazily
	def _make_cg() -> AttackHandler:
		from .code_glyph import get_code_glyph_attack  # lazy factory from package module
		CG = get_code_glyph_attack()
		return CG()  # type: ignore
	_REGISTRY_FACTORY["CODE_GLYPH"] = _make_cg


def get_attack_handler(name: str) -> AttackHandler | None:
	if not _REGISTRY_FACTORY:
		_register_defaults()
	if name in _REGISTRY:
		return _REGISTRY[name]
	factory = _REGISTRY_FACTORY.get(name)
	if not factory:
		return None
	try:
		h = factory()
		_REGISTRY[name] = h
		return h
	except Exception:
		return None 