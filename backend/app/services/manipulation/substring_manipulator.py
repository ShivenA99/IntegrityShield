from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class SubstringMapping:
    original: str
    replacement: str
    start_pos: int
    end_pos: int
    context: str = ""
    character_mappings: Dict[str, str] | None = None


class SubstringManipulator:
    def __init__(self) -> None:
        pass

    def _token_map(self, token: str, character_map: Dict[str, str]) -> str:
        return "".join(character_map.get(char, char) for char in token)

    def apply_character_map(self, token: str, character_map: Dict[str, str]) -> str:
        return self._token_map(token, character_map)

    def generate_mappings(self, text: str, character_map: Dict[str, str], context: str) -> List[Dict]:
        if not text:
            return []

        mappings: List[Dict] = []
        cursor = 0

        for token in text.split():
            index = text.find(token, cursor)
            if index == -1:
                continue

            replaced = self._replace_characters(token, character_map)
            if replaced != token:
                mapping = SubstringMapping(
                    original=token,
                    replacement=replaced,
                    start_pos=index,
                    end_pos=index + len(token),
                    context=context,
                    character_mappings={char: character_map.get(char, char) for char in token if char in character_map},
                )
                mappings.append(mapping.__dict__)

            cursor = index + len(token)

        return mappings

    def _replace_characters(self, token: str, character_map: Dict[str, str]) -> str:
        return "".join(character_map.get(char, char) for char in token)

    def validate_non_overlapping(self, mappings: List[Dict]) -> None:
        """Raise ValueError if any mapping ranges overlap or are invalid.
        Expects each mapping to have start_pos (inclusive) and end_pos (exclusive).
        """
        intervals: List[Tuple[int, int]] = []
        for m in mappings:
            s = int(m.get("start_pos", -1))
            e = int(m.get("end_pos", -1))
            if s < 0 or e <= s:
                raise ValueError("Invalid mapping range: start_pos/end_pos")
            intervals.append((s, e))
        intervals.sort()
        for i in range(1, len(intervals)):
            prev_e = intervals[i - 1][1]
            cur_s = intervals[i][0]
            if cur_s < prev_e:
                raise ValueError("Overlapping substring mappings are not allowed")

    def apply_mappings_to_text(self, text: str, mappings: List[Dict]) -> str:
        """Apply non-overlapping substring mappings to text.
        Mappings must be non-overlapping, defined with absolute indices on the original text.
        Replacements are applied from right-to-left to preserve indices.
        """
        if not mappings:
            return text
        self.validate_non_overlapping(mappings)

        # Sort by start descending so index offsets do not shift earlier edits
        sorted_maps = sorted(mappings, key=lambda m: int(m["start_pos"]), reverse=True)
        buf = text
        for m in sorted_maps:
            s = int(m["start_pos"])
            e = int(m["end_pos"])
            repl = str(m.get("replacement", ""))
            buf = buf[:s] + repl + buf[e:]
        return buf
