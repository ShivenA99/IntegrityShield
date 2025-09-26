from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict


def get_step_logger(base_dir: Path, step: str) -> logging.Logger:
	logger = logging.getLogger(f"new_ocr.{step}")
	logger.setLevel(logging.INFO)
	# Attach a file handler per step (non-duplicating)
	log_dir = Path(base_dir)
	log_dir.mkdir(parents=True, exist_ok=True)
	fh_path = log_dir / f"{step}.log"
	if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', '').endswith(str(fh_path)) for h in logger.handlers):
		fh = logging.FileHandler(str(fh_path), mode="a", encoding="utf-8")
		fh.setLevel(logging.INFO)
		formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s")
		fh.setFormatter(formatter)
		logger.addHandler(fh)
	return logger


def save_json(base_dir: Path, name: str, obj: Dict[str, Any]) -> Path:
	p = Path(base_dir) / f"{name}.json"
	with open(p, "w", encoding="utf-8") as f:
		json.dump(obj, f, ensure_ascii=False, indent=2)
	return p 