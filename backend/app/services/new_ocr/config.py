import os
from dataclasses import dataclass


@dataclass
class NewOCRConfig:
	NEW_OCR: bool = os.getenv("NEW_OCR", "1") in {"1", "true", "True"}
	OCR_VECTOR_MODE: str = os.getenv("OCR_VECTOR_MODE", "vector").strip().lower()
	OCR_PAGE_CONCURRENCY: int = int(os.getenv("OCR_PAGE_CONCURRENCY", "2"))
	OCR_TIMEOUT_S: int = int(os.getenv("OCR_TIMEOUT_S", "120"))
	OCR_MAX_REGION_AUG_PER_PAGE: int = int(os.getenv("OCR_MAX_REGION_AUG_PER_PAGE", "3"))
	MISTRAL_API_KEY: str | None = os.getenv("MISTRAL_API_KEY")
	MISTRAL_MODEL: str = os.getenv("MISTRAL_MODEL", "mistral-small-latest")
	OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
	OPENAI_VISION_MODEL: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
	OCR_USE_OPENAI_VISION: bool = os.getenv("OCR_USE_OPENAI_VISION", "1") in {"1", "true", "True"}
	STRUCTURE_OCR_DPI: int = int(os.getenv("STRUCTURE_OCR_DPI", "300"))


def summarize_config() -> dict:
	cfg = NewOCRConfig()
	return {
		"NEW_OCR": cfg.NEW_OCR,
		"OCR_VECTOR_MODE": cfg.OCR_VECTOR_MODE,
		"OCR_PAGE_CONCURRENCY": cfg.OCR_PAGE_CONCURRENCY,
		"OCR_TIMEOUT_S": cfg.OCR_TIMEOUT_S,
		"OCR_MAX_REGION_AUG_PER_PAGE": cfg.OCR_MAX_REGION_AUG_PER_PAGE,
		"MISTRAL_MODEL": cfg.MISTRAL_MODEL,
		"OPENAI_VISION_MODEL": cfg.OPENAI_VISION_MODEL,
		"OCR_USE_OPENAI_VISION": cfg.OCR_USE_OPENAI_VISION,
		"STRUCTURE_OCR_DPI": cfg.STRUCTURE_OCR_DPI,
	} 