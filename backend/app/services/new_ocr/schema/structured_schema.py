from __future__ import annotations

import logging
from typing import Any, Dict, List

try:
	from pydantic import BaseModel, Field, ValidationError
except Exception:
	BaseModel = object  # type: ignore
	Field = lambda *a, **k: None  # type: ignore
	ValidationError = Exception  # type: ignore

logger = logging.getLogger(__name__)


class TextBlock(BaseModel):
	id: str
	type: str = "text_block"
	bbox: List[float]
	text: str
	markdown: str | None = None
	index_map: List[dict] | None = None


class ImageItem(BaseModel):
	id: str
	type: str = "image"
	bbox: List[float]
	asset_id: str
	orig_mime: str | None = None


class Page(BaseModel):
	page_index: int
	width: float
	height: float
	rotation: int | None = 0
	items: List[dict]


class Meta(BaseModel):
	source_path: str
	dpi: int
	num_pages: int
	extractor_versions: Dict[str, str] = Field(default_factory=dict)
	vendor_versions: Dict[str, str] = Field(default_factory=dict)


class StructuredDoc(BaseModel):
	meta: Meta
	document: Dict[str, Any]


def validate_structured_json(obj: Dict[str, Any]) -> bool:
	try:
		StructuredDoc(**obj)
		return True
	except ValidationError as e:
		logger.error("[NEW_OCR][SCHEMA] Validation failed: %s", e)
		return False 