from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from fontTools.ttLib import TTFont
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.transformPen import TransformPen

from .chunking import AttackPlan, AttackPosition, GlyphLookup


class FontBuildError(RuntimeError):
    """Raised when a derivative font cannot be created."""


@dataclass(frozen=True)
class FontBuildResult:
    index: int
    hidden_char: str
    visual_text: str
    font_path: Path
    used_cache: bool = False


class FontAttackBuilder:
    """Clone a baseline TrueType font for each attack position."""

    def __init__(self, base_font_path: Path) -> None:
        self.base_font_path = Path(base_font_path)
        if not self.base_font_path.exists():
            raise FileNotFoundError(f"Base font not found at {self.base_font_path}")

        self._base_font = TTFont(str(self.base_font_path))
        if "glyf" not in self._base_font or "hmtx" not in self._base_font:
            raise FontBuildError("Base font must contain 'glyf' and 'hmtx' tables")

        self._glyph_lookup = GlyphLookup(
            cmap=self._base_font.getBestCmap(),
            hmtx=self._base_font["hmtx"].metrics,
        )
        self._glyph_set = self._base_font.getGlyphSet()

    @property
    def glyph_lookup(self) -> GlyphLookup:
        return self._glyph_lookup

    def build_fonts(
        self,
        plan: AttackPlan,
        output_dir: Path,
        cache_lookup: Optional["FontCache"] = None,
    ) -> Sequence[FontBuildResult]:
        output_dir.mkdir(parents=True, exist_ok=True)

        results: list[FontBuildResult] = []
        for position in plan:
            if not position.requires_font:
                continue

            cache_key = self._derive_cache_key(position)
            cached_path: Optional[Path] = None
            if cache_lookup:
                cached_path = cache_lookup.resolve(cache_key, output_dir)

            if cached_path and cached_path.exists():
                results.append(
                    FontBuildResult(
                        index=position.index,
                        hidden_char=position.hidden_char,
                        visual_text=position.visual_text,
                        font_path=cached_path,
                        used_cache=True,
                    )
                )
                continue

            font_path = output_dir / f"attack_pos{position.index}.ttf"
            self._write_position_font(position, font_path)
            if cache_lookup:
                cache_lookup.store(cache_key, font_path)

            results.append(
                FontBuildResult(
                    index=position.index,
                    hidden_char=position.hidden_char,
                    visual_text=position.visual_text,
                    font_path=font_path,
                    used_cache=False,
                )
            )
        return tuple(results)

    def _write_position_font(self, position: AttackPosition, path: Path) -> None:
        font = TTFont(str(self.base_font_path))
        glyph_table = font["glyf"]
        metrics_table = font["hmtx"]

        hidden_glyph = self._glyph_lookup.glyph_name(position.hidden_char)
        pen = TTGlyphPen(self._glyph_set)
        x_offset = 0
        total_width = 0

        for glyph_name in position.glyph_names:
            glyph = self._glyph_set[glyph_name]
            transform = TransformPen(pen, (1, 0, 0, 1, x_offset, 0))
            glyph.draw(transform)
            width, _ = metrics_table.metrics.get(glyph_name, (0, 0))
            x_offset += width
            total_width += width

        new_glyph = pen.glyph()
        glyph_table[hidden_glyph] = new_glyph

        old_advance, old_lsb = metrics_table.metrics.get(hidden_glyph, (0, 0))
        advance_width = int(round(total_width))
        if position.is_zero_width:
            advance_width = 0
            old_lsb = 0
        metrics_table.metrics[hidden_glyph] = (advance_width or old_advance, old_lsb)

        font.save(str(path))

    def _derive_cache_key(self, position: AttackPosition) -> str:
        digest = hashlib.sha256()
        digest.update(self.base_font_path.name.encode("utf-8"))
        digest.update(position.hidden_char.encode("utf-8"))
        digest.update(position.visual_text.encode("utf-8"))
        digest.update(str(int(round(position.advance_width))).encode("utf-8"))
        return digest.hexdigest()


class FontCache:
    """Simple file-based cache keyed by SHA-256 digests."""

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, key: str, output_dir: Path) -> Optional[Path]:
        candidate = self.storage_dir / f"{key}.ttf"
        if candidate.exists():
            target = output_dir / candidate.name
            if not target.exists():
                target.write_bytes(candidate.read_bytes())
            return target
        return None

    def store(self, key: str, font_path: Path) -> None:
        destination = self.storage_dir / f"{key}.ttf"
        if not destination.exists():
            destination.write_bytes(font_path.read_bytes())
