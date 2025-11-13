from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class AttackPosition:
    """Visual content assigned to a single hidden character."""

    index: int
    hidden_char: str
    visual_text: str
    glyph_names: Sequence[str]
    advance_width: float

    @property
    def requires_font(self) -> bool:
        if not self.visual_text:
            return True
        return not (
            len(self.visual_text) == 1 and self.visual_text == self.hidden_char
        )

    @property
    def is_zero_width(self) -> bool:
        return not self.visual_text


@dataclass(frozen=True)
class AttackPlan:
    """Distribution of visual glyphs across hidden text positions."""

    positions: Sequence[AttackPosition]

    def __iter__(self):
        return iter(self.positions)

    def __len__(self) -> int:
        return len(self.positions)


class ChunkPlanner:
    """
    Assign visual glyphs to each hidden character so that the rendered output
    matches the visual text irrespective of length differences.
    """

    def __init__(self, glyph_lookup: "GlyphLookup") -> None:
        self._glyph_lookup = glyph_lookup

    def plan(self, hidden_text: str, visual_text: str) -> AttackPlan:
        if not hidden_text:
            raise ValueError("Hidden text must be non-empty")

        hidden_chars = list(hidden_text)
        visual_chars = list(visual_text)

        for char in set(hidden_chars + visual_chars):
            self._glyph_lookup.ensure_available(char)

        positions: List[AttackPosition] = []

        if not visual_chars:
            positions.extend(
                self._blank_position(idx, char) for idx, char in enumerate(hidden_chars)
            )
            return AttackPlan(tuple(positions))

        if len(hidden_chars) >= len(visual_chars):
            positions.extend(self._plan_when_hidden_longer(hidden_chars, visual_chars))
        else:
            positions.extend(
                self._plan_when_visual_longer(hidden_chars, visual_chars)
            )

        return AttackPlan(tuple(positions))

    def _plan_when_hidden_longer(
        self,
        hidden_chars: Sequence[str],
        visual_chars: Sequence[str],
    ) -> Iterable[AttackPosition]:
        visual_index = 0
        visual_length = len(visual_chars)
        pending_spaces: List[str] = []

        for idx, hidden_char in enumerate(hidden_chars):
            if hidden_char.isspace():
                token: Optional[str] = None
                if pending_spaces:
                    token = pending_spaces.pop(0)
                elif visual_index < visual_length and visual_chars[visual_index].isspace():
                    token = visual_chars[visual_index]
                    visual_index += 1
                if token is None:
                    token = " "
                glyph_name = self._glyph_lookup.glyph_name(token)
                width = self._glyph_lookup.glyph_width(token)
                yield AttackPosition(
                    index=idx,
                    hidden_char=hidden_char,
                    visual_text=token,
                    glyph_names=(glyph_name,),
                    advance_width=width,
                )
                continue

            while visual_index < visual_length and visual_chars[visual_index].isspace():
                pending_spaces.append(visual_chars[visual_index])
                visual_index += 1

            if visual_index < visual_length:
                visual_char = visual_chars[visual_index]
                visual_index += 1
                glyph_name = self._glyph_lookup.glyph_name(visual_char)
                width = self._glyph_lookup.glyph_width(visual_char)
                yield AttackPosition(
                    index=idx,
                    hidden_char=hidden_char,
                    visual_text=visual_char,
                    glyph_names=(glyph_name,),
                    advance_width=width,
                )
            else:
                yield self._blank_position(idx, hidden_char)

    def _plan_when_visual_longer(
        self,
        hidden_chars: Sequence[str],
        visual_chars: Sequence[str],
    ) -> Iterable[AttackPosition]:
        total_visual_width = sum(
            self._glyph_lookup.glyph_width(char) for char in visual_chars
        )
        target_width = total_visual_width / max(len(hidden_chars), 1)

        positions: List[AttackPosition] = []
        v_index = 0
        for idx, hidden_char in enumerate(hidden_chars):
            remaining_slots = len(hidden_chars) - idx
            if remaining_slots == 0:
                break

            remaining_visual = len(visual_chars) - v_index
            take_limit = remaining_visual - (remaining_slots - 1)
            take_limit = max(take_limit, 1)

            chunk_chars: List[str] = []
            chunk_glyphs: List[str] = []
            chunk_width = 0.0
            taken = 0

            while v_index < len(visual_chars) and taken < take_limit:
                char = visual_chars[v_index]
                glyph_name = self._glyph_lookup.glyph_name(char)
                width = self._glyph_lookup.glyph_width(char)
                chunk_chars.append(char)
                chunk_glyphs.append(glyph_name)
                chunk_width += width
                v_index += 1
                taken += 1
                remaining_visual_after_take = len(visual_chars) - v_index
                if (
                    chunk_width >= target_width
                    and remaining_visual_after_take >= remaining_slots - 1
                ):
                    break

            if idx == len(hidden_chars) - 1 and v_index < len(visual_chars):
                while v_index < len(visual_chars):
                    char = visual_chars[v_index]
                    glyph_name = self._glyph_lookup.glyph_name(char)
                    width = self._glyph_lookup.glyph_width(char)
                    chunk_chars.append(char)
                    chunk_glyphs.append(glyph_name)
                    chunk_width += width
                    v_index += 1

            positions.append(
                AttackPosition(
                    index=idx,
                    hidden_char=hidden_char,
                    visual_text="".join(chunk_chars),
                    glyph_names=tuple(chunk_glyphs),
                    advance_width=chunk_width,
                )
            )

        while len(positions) < len(hidden_chars):
            idx = len(positions)
            positions.append(self._blank_position(idx, hidden_chars[idx]))

        return positions

    def _blank_position(self, index: int, hidden_char: str) -> AttackPosition:
        return AttackPosition(
            index=index,
            hidden_char=hidden_char,
            visual_text="",
            glyph_names=(),
            advance_width=0.0,
        )


class GlyphLookup:
    """Convenience wrapper that exposes glyph metrics."""

    def __init__(self, cmap, hmtx) -> None:
        self._cmap = cmap
        self._hmtx = hmtx

    def ensure_available(self, char: str) -> None:
        if ord(char) not in self._cmap:
            raise KeyError(f"Glyph for character '{char}' not found in base font")

    def glyph_name(self, char: str) -> str:
        codepoint = ord(char)
        glyph_name = self._cmap.get(codepoint)
        if glyph_name is None:
            raise KeyError(f"No glyph name for code point {codepoint}")
        return glyph_name

    def glyph_width(self, char: str) -> float:
        glyph_name = self.glyph_name(char)
        advance, _lsb = self._hmtx.get(glyph_name, (0, 0))
        return float(advance)
