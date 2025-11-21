from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from uuid import uuid4


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "which",
    "into",
    "over",
    "under",
    "about",
    "after",
    "before",
    "through",
    "than",
    "among",
    "during",
    "while",
    "because",
    "since",
    "when",
    "where",
    "what",
    "how",
    "have",
    "will",
    "would",
    "could",
    "should",
    "might",
    "also",
    "many",
    "most",
    "much",
    "more",
    "less",
    "been",
    "being",
    "such",
    "other",
    "like",
    "some",
    "any",
    "each",
    "every",
    "either",
    "neither",
    "only",
    "very",
    "just",
    "even",
}


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    generation_focus: str
    validation_focus: str
    examples: Sequence[str]
    keyword_swaps: Sequence[Tuple[str, str]]
    default_replacement: str


_GLOBAL_KEYWORD_SWAPS: Sequence[Tuple[str, str]] = (
    ("primary", "secondary"),
    ("main", "minor"),
    ("increase", "decrease"),
    ("decrease", "increase"),
    ("maximize", "minimize"),
    ("most", "least"),
    ("best", "worst"),
    ("advantage", "drawback"),
    ("benefit", "risk"),
    ("support", "undermine"),
    ("should", "should not"),
    ("can", "cannot"),
    ("true", "false"),
    ("positive", "negative"),
    ("long-term", "short-term"),
    ("higher", "lower"),
    ("lower", "higher"),
)


TARGET_STRATEGY_TYPES = {
    "mcq_single",
    "mcq_multi",
    "true_false",
    "matching",
}

SIGNAL_STRATEGY_TYPES = {
    "fill_blank",
    "short_answer",
    "long_answer",
    "comprehension_qa",
}

_MCQ_FEW_SHOT_EXAMPLES = """
Example (Q2 — polynomial growth MCQ):
Stem excerpt: "If T(n) = 5n^3 + 4n + 1, which might be the correct expression for O(T(n)) under Landau’s notation?)"
Gold answer: "B"
Chosen wrong target: "D" → "O(n^5)"
Return JSON:
{
  "mappings": [
    {
      "original": "the correct",
      "replacement": "nsquared times the",
      "start_pos": 40,
      "end_pos": 51,
      "context": "question_stem",
      "target_option": "D",
      "target_option_text": "O(n^5)"
    }
  ]
}

Example (Q6 — sorting MCQ with two edits):
Stem excerpt: "When an array is already sorted, which sorting algorithm run in O(n) time if implemented with slight optimizations?)"
Gold answer: "B"
Chosen wrong target: "A" → "Selection Sort"
Return JSON where both mappings share the same target metadata:
{
  "mappings": [
    {
      "original": "already",
      "replacement": "not",
      "start_pos": 17,
      "end_pos": 24,
      "context": "question_stem",
      "target_option": "A",
      "target_option_text": "Selection Sort"
    },
    {
      "original": "implemented with slight",
      "replacement": "executed in swap-costly",
      "start_pos": 77,
      "end_pos": 100,
      "context": "question_stem",
      "target_option": "A",
      "target_option_text": "Selection Sort"
    }
  ]
}

Example (Q8 — tree balancing MCQ):
Single-span swap `crucial → irrelevant` pointing to target option "A" ("Ensuring each node has exactly one child").

Example (Q9 — heap indexing MCQ):
Swap `describe → misdescribe` targeting option "A" (array parent-offset explanation).

Example (Q10 — heap invariant MCQ):
Swap `always → never` targeting option "C" ("The tree is guaranteed to be a balanced binary search tree").
"""

_SIGNAL_GUIDANCE = """
Signal mapping template:
{
  "mappings": [
    {
      "original": "benefit",
      "replacement": "risk",
      "start_pos": 42,
      "end_pos": 49,
      "context": "question_stem",
      "signal_type": "keyword",
      "signal_phrase": "risk of gradient clipping",
      "signal_notes": "Detector should flag answers highlighting this risk"
    }
  ]
}
- Always include `signal_type`, `signal_phrase`, and `signal_notes`.
- Do not emit `target_option` fields for signal-driven questions.
"""

_STRATEGIES: Dict[str, StrategyDefinition] = {
    "mcq_single": StrategyDefinition(
        key="mcq_single",
        generation_focus=(
            "Flip a crucial qualifier or verb in the stem so the original correct option becomes wrong."
        ),
        validation_focus=(
            "The expected manipulated response should select a different option letter than the gold answer."
        ),
        examples=(
            "Original: 'What is the primary benefit of X?' → Replacement: 'What is the secondary benefit of X?'",
            "Original: 'Which factor increases Y?' → Replacement: 'Which factor decreases Y?'",
        ),
        keyword_swaps=_GLOBAL_KEYWORD_SWAPS,
        default_replacement="not",
    ),
    "short_answer": StrategyDefinition(
        key="short_answer",
        generation_focus=(
            "Nudge the stem toward the opposite conclusion so the concise written answer changes meaning."
        ),
        validation_focus=(
            "Expect the model to produce a short textual answer that contradicts the original gold response."
        ),
        examples=(
            "Original: 'Explain why the gradient explodes when ... > 1' → Replace '> 1' with '< 1'.",
            "Original: 'Describe the benefit of forget gates' → Replace 'benefit' with 'risk'.",
        ),
        keyword_swaps=_GLOBAL_KEYWORD_SWAPS
        + (
            ("advantage", "limitation"),
            ("strength", "weakness"),
            ("cause", "prevent"),
        ),
        default_replacement="incorrect",
    ),
}


def get_strategy(question_type: str) -> StrategyDefinition:
    return _STRATEGIES.get(question_type, _STRATEGIES["mcq_single"])


def _match_replacement_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[0].isupper() and original[1:].islower():
        return replacement.capitalize()
    return replacement


def build_index_reference(text: str, limit: int = 320) -> str:
    trimmed = text[:limit]
    rows: List[str] = []
    bucket: List[str] = []
    for idx, ch in enumerate(trimmed):
        if ch == " ":
            display = "␠"
        elif ch == "\n":
            display = "\\n"
        elif ch == "\t":
            display = "\\t"
        elif ch == "\r":
            display = "\\r"
        else:
            display = ch
        bucket.append(f"{idx:03}:{display}")
        if len(bucket) == 8:
            rows.append(" ".join(bucket))
            bucket = []
    if bucket:
        rows.append(" ".join(bucket))
    if len(text) > limit:
        rows.append(f"… truncated after {limit} characters")
    return "\n".join(rows)


def build_generation_prompt(
    stem_text: str,
    question_type: str,
    gold_answer: Optional[str],
    options_block: str,
    strategy: StrategyDefinition,
    index_reference: str,
    safe_span_entries: Optional[List[Dict[str, str]]] = None,
    max_candidates: int = 1,
) -> str:
    examples = "\n".join(f"- {line}" for line in strategy.examples)
    candidate_line = "Provide exactly one mapping candidate." if max_candidates <= 1 else (
        f"Provide up to {max_candidates} candidate mapping objects in the 'mappings' array, sorted best-to-worst."
    )
    prompt_lines = [
        "You are designing subtle adversarial substitutions for assessment questions.",
        "Return strictly valid JSON with a top-level \"mappings\" array.",
        "Each mapping object must include: original, replacement, start_pos, end_pos, context (always \"question_stem\").",
        "Use 0-based character offsets from the exact Stem text below (end_pos exclusive).",
        "The substring stem_text[start_pos:end_pos] MUST match the \"original\" value exactly (including case).",
        "CRITICAL: The replacement MUST be DIFFERENT from the original. Do NOT generate mappings where original == replacement (e.g., \"power\" → \"power\" is INVALID). The replacement MUST change the text to create actual manipulation.",
        "CRITICAL: Neither original nor replacement can be empty strings. Both must contain actual text.",
        "Keep each mapping within a single contiguous span of characters; do not skip over other words or newlines.",
        "Never overlap mappings and prefer one precise change over many scattered edits.",
        "If you introduce spaces in the replacement, include them explicitly so the surrounding words remain intact.",
        "Do not duplicate neighboring words (e.g., avoid turning 'is the' into 'is is not the').",
    ]

    if question_type in TARGET_STRATEGY_TYPES or question_type not in SIGNAL_STRATEGY_TYPES:
        prompt_lines.extend(
            [
                "Before proposing a mapping, choose exactly one answer option other than the gold answer that you want to become correct.",
                "Craft the edit so the modified stem clearly supports that chosen option while contradicting the original gold option.",
                "Include both \"target_option\" (letter) and \"target_option_text\" (full option text) in every mapping object.",
                "If multiple mappings are required to land on the same outcome, reuse the identical target metadata in each object.",
                "Target-based few-shot references:",
                _MCQ_FEW_SHOT_EXAMPLES.strip(),
                "",
            ]
        )
    if question_type in SIGNAL_STRATEGY_TYPES:
        prompt_lines.extend(
            [
                "For this question type, generate a signal instead of a discrete target.",
                "Each mapping must include \"signal_type\", \"signal_phrase\", and \"signal_notes\" explaining what detectors should look for.",
                "Omit any target-related fields when emitting a signal mapping.",
                "Signal mapping template:",
                _SIGNAL_GUIDANCE.strip(),
                "",
            ]
        )

    prompt_lines.extend(
        [
            candidate_line,
            f"Strategy focus: {strategy.generation_focus}",
            f"Validation focus: {strategy.validation_focus}",
            "Examples:",
            examples,
            "",
            f"Question type: {question_type}",
            f"Gold answer: {gold_answer or 'unknown'}",
            "Stem:",
            stem_text,
            "",
            "Character index reference (␠ = space):",
            index_reference,
            "",
            "Options:" if options_block else "Options: None provided",
        ]
    )
    if options_block:
        prompt_lines.append(options_block)
    prompt_lines.extend(
        [
            "",
            "Respond ONLY with JSON that matches {\"mappings\": [...]}.",
            "Example response: {\"mappings\":[{\"original\":\"is the\",\"replacement\":\"is not the\",\"start_pos\":23,\"end_pos\":29,\"context\":\"question_stem\"}]}"
        ]
    )
    if safe_span_entries:
        prompt_lines.extend(
            [
                "",
                "Safe substrings from the PDF (choose originals only from this list; match the characters exactly, including missing spaces):",
            ]
        )
        prompt_lines.append(
            "- Each bullet below is the exact text of a single PDF span; treat it as an atomic chunk."
        )
        prompt_lines.append(
            "- Choose originals directly from one bullet only. Do not join multiple bullets or add extra characters around them."
        )
        prompt_lines.append(
            "- If no single bullet matches the wording you need, return {\"mappings\": []}."
        )
        for span in safe_span_entries[:80]:
            span_id = span.get("span_id") or "unknown"
            raw_text = span.get("text") or ""
            normalized_text = span.get("normalized") or ""
            display = raw_text if raw_text else normalized_text
            if len(display) > 60:
                display = f"{display[:57]}..."
            if normalized_text and normalized_text != raw_text:
                normalized_display = normalized_text if len(normalized_text) <= 60 else f"{normalized_text[:57]}..."
                prompt_lines.append(f"- {span_id}: raw=\"{display}\", normalized=\"{normalized_display}\"")
            else:
                prompt_lines.append(f"- {span_id}: \"{display}\"")
        prompt_lines.extend(
            [
                "",
                "If none of the safe substrings above contain a suitable original text, return {\"mappings\": []}.",
            ]
        )
    return "\n".join(prompt_lines)


def _iter_keyword_swaps(strategy: StrategyDefinition) -> Iterable[Tuple[str, str]]:
    seen: set[Tuple[str, str]] = set()
    for item in strategy.keyword_swaps:
        if item not in seen:
            seen.add(item)
            yield item
    for item in _GLOBAL_KEYWORD_SWAPS:
        if item not in seen:
            seen.add(item)
            yield item


def _search_keyword_swap(text: str, strategy: StrategyDefinition) -> Optional[Tuple[str, str, int, int, str]]:
    lowered = text.lower()
    for original, replacement in _iter_keyword_swaps(strategy):
        pattern = re.escape(original.lower())
        match = re.search(pattern, lowered)
        if not match:
            continue
        start, end = match.span()
        actual = text[start:end]
        replacement_token = _match_replacement_case(actual, replacement)
        return actual, replacement_token, start, end, "keyword_flip"
    return None


def _fallback_word_substitution(text: str, default_replacement: str) -> Optional[Tuple[str, str, int, int, str]]:
    for match in re.finditer(r"[A-Za-z]{3,}", text):
        token = match.group(0)
        if token.lower() in _STOPWORDS:
            continue
        start, end = match.span()
        replacement = f"{default_replacement} {token}" if default_replacement == "not" else default_replacement
        return token, replacement, start, end, "fallback_negation"
    return None


def generate_heuristic_mappings(
    stem_text: str,
    question_type: str,
    strategy: StrategyDefinition,
) -> Tuple[List[Dict[str, object]], str]:
    if not stem_text:
        return [], "no_text"

    candidate = _search_keyword_swap(stem_text, strategy)
    if candidate is None:
        candidate = _fallback_word_substitution(stem_text, strategy.default_replacement)

    if candidate is None:
        return [], "unavailable"

    original, replacement, start, end, method = candidate
    mapping = {
        "id": uuid4().hex[:10],
        "original": original,
        "replacement": replacement,
        "start_pos": start,
        "end_pos": end,
        "context": "question_stem",
    }
    return [mapping], method


def describe_strategy_for_validation(strategy: StrategyDefinition) -> str:
    return strategy.validation_focus
