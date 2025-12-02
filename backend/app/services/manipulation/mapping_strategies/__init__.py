from __future__ import annotations

import random
import string
from typing import Callable, Dict


def _unicode_steganography() -> Dict[str, str]:
    return {
        "A": "А",
        "B": "В",
        "C": "С",
        "E": "Е",
        "H": "Н",
        "K": "К",
        "M": "М",
        "O": "О",
        "P": "Р",
        "T": "Т",
        "X": "Х",
        "Y": "Ү",
        "a": "а",
        "c": "с",
        "e": "е",
        "o": "о",
        "p": "р",
        "x": "х",
        "y": "у",
    }


def _mathematical_variants() -> Dict[str, str]:
    return {
        "A": "𝐀",
        "B": "𝐁",
        "C": "𝐂",
        "D": "𝐃",
        "E": "𝐄",
        "F": "𝐅",
        "G": "𝐆",
        "H": "𝐇",
        "I": "𝐈",
        "J": "𝐉",
        "a": "𝑎",
        "b": "𝑏",
        "c": "𝑐",
        "d": "𝑑",
        "e": "𝑒",
        "f": "𝑓",
        "g": "𝑔",
        "h": "ℎ",
    }


def _fullwidth_forms() -> Dict[str, str]:
    return {chr(code): chr(code + 0xFEE0) for code in range(0x21, 0x7F)}


def _homoglyph_confusion() -> Dict[str, str]:
    return {
        "0": "𝟢",
        "1": "𝟣",
        "2": "𝟤",
        "3": "𝟥",
        "4": "𝟦",
        "5": "𝟧",
        "6": "𝟨",
        "7": "𝟩",
        "8": "𝟪",
        "9": "𝟫",
        "!": "ǃ",
        "?": "ꙮ",
        "-": "‐",
    }


ASCII_PRINTABLE = string.printable[:95]


def _ascii_shift(shift: int = 13) -> Dict[str, str]:
    return {ch: ASCII_PRINTABLE[(i + shift) % len(ASCII_PRINTABLE)] for i, ch in enumerate(ASCII_PRINTABLE)}


def _ascii_reverse() -> Dict[str, str]:
    return {ch: ASCII_PRINTABLE[::-1][i] for i, ch in enumerate(ASCII_PRINTABLE)}


def _ascii_shuffle(seed: int = 42) -> Dict[str, str]:
    random.seed(seed)
    shuffled = list(ASCII_PRINTABLE)
    random.shuffle(shuffled)
    return {ch: shuffled[i] for i, ch in enumerate(ASCII_PRINTABLE)}


def _rot13_extended() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for ch in ASCII_PRINTABLE:
        if ch.islower():
            mapping[ch] = chr((ord(ch) - ord("a") + 13) % 26 + ord("a"))
        elif ch.isupper():
            mapping[ch] = chr((ord(ch) - ord("A") + 13) % 26 + ord("A"))
        elif ch.isdigit():
            mapping[ch] = str((int(ch) + 5) % 10)
        else:
            ascii_val = ord(ch)
            if 32 <= ascii_val <= 47:
                new_val = 32 + ((ascii_val - 32 + 7) % 16)
            elif 58 <= ascii_val <= 64:
                new_val = 58 + ((ascii_val - 58 + 3) % 7)
            elif 91 <= ascii_val <= 96:
                new_val = 91 + ((ascii_val - 91 + 2) % 6)
            elif 123 <= ascii_val <= 126:
                new_val = 123 + ((ascii_val - 123 + 1) % 4)
            else:
                new_val = ascii_val
            mapping[ch] = chr(new_val)
    return mapping


_GENERATORS: Dict[str, Callable[[], Dict[str, str]]] = {
    "unicode_steganography": _unicode_steganography,
    "mathematical_variants": _mathematical_variants,
    "fullwidth_forms": _fullwidth_forms,
    "homoglyph_confusion": _homoglyph_confusion,
    "ascii_shift": _ascii_shift,
    "ascii_reverse": _ascii_reverse,
    "ascii_shuffle": _ascii_shuffle,
    "rot13_extended": _rot13_extended,
}


def load_strategy_mapping(strategy: str) -> Dict[str, str]:
    if strategy not in _GENERATORS:
        raise ValueError(f"Unknown mapping strategy: {strategy}")
    generator = _GENERATORS[strategy]
    return dict(generator())
