"""Prompt templates for mapping generation."""

MCQ_REPLACEMENT_PROMPT = """You are an expert at generating text substitutions for academic multiple-choice questions.

Given:
- LaTeX code for the question stem: {latex_stem_text}
- Gold answer: {gold_answer}
- Question type: {question_type}
- Options: {options}
- Strategy: replacement
- Reasoning steps:
{reasoning_steps}
- Copyable text (use this exact text when selecting substrings):
<<<COPY
{copyable_text}
>>>
{prefix_note}{answer_guidance}{retry_instructions}

Your task:
Generate {k} valid mappings that satisfy the replacement strategy. Each mapping should:
1. Replace one contiguous substring of the question stem
2. Change the answer from the gold option ({gold_answer}) to a different incorrect option
3. Ensure the replacement is semantically meaningful and natural
4. Cause a verifiable deviation in the answer

For each mapping, provide:
1. question_index: The question number ({question_index})
2. latex_stem_text: Exact LaTeX text of the question stem (must match the input exactly)
3. original_substring: The substring to replace (must be a contiguous substring of latex_stem_text)
4. replacement_substring: The replacement text
5. start_pos: Start position of original_substring relative to latex_stem_text (0-based index)
6. end_pos: End position of original_substring relative to latex_stem_text (exclusive, 0-based index)
7. target_wrong_answer: The target incorrect option label (e.g., "B", "C", "D")
8. reasoning: Brief explanation of why this mapping satisfies the strategy

IMPORTANT:
- The original_substring MUST be an exact substring of latex_stem_text
- The start_pos and end_pos MUST be accurate (start_pos + len(original_substring) = end_pos)
- The target_wrong_answer MUST be different from the gold answer
- CRITICAL: The replacement_substring MUST be DIFFERENT from the original_substring. Do NOT generate mappings where original_substring == replacement_substring (e.g., "power" → "power" is INVALID). The replacement MUST change the text to create actual manipulation.
- CRITICAL: Neither original_substring nor replacement_substring can be empty strings. Both must contain actual text.
- LENGTH CONSTRAINT: The replacement_substring MUST be smaller or equal in length to the original_substring (len(replacement_substring) <= len(original_substring)). This is critical for maintaining document layout and preventing text overflow.
- latex_stem_text is provided exactly as it appears in the LaTeX source. Do NOT trim, normalise, or reformat it when determining positions.
- The latex_stem_text may include \item tokens from enumerate environments. Keep the \item token intact and operate on the descriptive text that follows it whenever possible.
- The replacement should be natural and semantically meaningful

Return as JSON array:
[
  {{
    "question_index": {question_index},
    "latex_stem_text": "...",
    "original_substring": "...",
    "replacement_substring": "...",
    "start_pos": 0,
    "end_pos": 5,
    "target_wrong_answer": "B",
    "reasoning": "..."
  }},
  ...
]

Return ONLY valid JSON, no markdown or additional text."""

TRUE_FALSE_REPLACEMENT_PROMPT = """You are an expert at generating text substitutions for True/False questions.

Given:
- LaTeX code for the question stem: {latex_stem_text}
- Gold answer: {gold_answer}
- Question type: {question_type}
- Strategy: replacement
- Reasoning steps:
{reasoning_steps}
- Copyable text (use this exact text when selecting substrings):
<<<COPY
{copyable_text}
>>>
{prefix_note}{answer_guidance}{retry_instructions}

Your task:
Generate {k} valid mappings that satisfy the replacement strategy. Each mapping should:
1. Replace one contiguous substring of the question stem
2. Flip the answer from {gold_answer} to the opposite answer
3. Ensure the replacement is semantically meaningful and natural
4. Cause a verifiable deviation in the answer

For each mapping, provide:
1. question_index: The question number ({question_index})
2. latex_stem_text: Exact LaTeX text of the question stem (must match the input exactly)
3. original_substring: The substring to replace (must be a contiguous substring of latex_stem_text)
4. replacement_substring: The replacement text
5. start_pos: Start position of original_substring relative to latex_stem_text (0-based index)
6. end_pos: End position of original_substring relative to latex_stem_text (exclusive, 0-based index)
7. target_wrong_answer: The opposite answer (e.g., "False" if gold is "True", or "True" if gold is "False")
8. reasoning: Brief explanation of why this mapping satisfies the strategy

IMPORTANT:
- The original_substring MUST be an exact substring of latex_stem_text
- The start_pos and end_pos MUST be accurate (start_pos + len(original_substring) = end_pos)
- The target_wrong_answer MUST be the opposite of the gold answer
- CRITICAL: The replacement_substring MUST be DIFFERENT from the original_substring. Do NOT generate mappings where original_substring == replacement_substring (e.g., "force" → "force" is INVALID). The replacement MUST change the text to create actual manipulation.
- CRITICAL: Neither original_substring nor replacement_substring can be empty strings. Both must contain actual text.
- LENGTH CONSTRAINT: The replacement_substring MUST be smaller or equal in length to the original_substring (len(replacement_substring) <= len(original_substring)). This is critical for maintaining document layout and preventing text overflow.
- latex_stem_text is provided exactly as it appears in the LaTeX source. Do NOT trim, normalise, or reformat it when determining positions.
- The latex_stem_text may include \item tokens from enumerate environments. Keep the \item token intact and operate on the descriptive text that follows it whenever possible.
- The replacement should be natural and semantically meaningful

Return as JSON array:
[
  {{
    "question_index": {question_index},
    "latex_stem_text": "...",
    "original_substring": "...",
    "replacement_substring": "...",
    "start_pos": 0,
    "end_pos": 5,
    "target_wrong_answer": "False",
    "reasoning": "..."
  }},
  ...
]

Return ONLY valid JSON, no markdown or additional text."""

LONG_FORM_REPLACEMENT_PROMPT = """You are an expert at generating text substitutions for long-form questions (essay, short answer, etc.).

Given:
- LaTeX code for the question stem: {latex_stem_text}
- Gold answer: {gold_answer}
- Question type: {question_type}
- Strategy: replacement
- Reasoning steps:
{reasoning_steps}
- Copyable text (use this exact text when selecting substrings):
<<<COPY
{copyable_text}
>>>
{prefix_note}{answer_guidance}{retry_instructions}

Your task:
Generate {k} valid mappings that satisfy the replacement strategy. Each mapping should:
1. Replace one contiguous substring of the question stem
2. Cause a verifiable and detectable deviation from the gold answer
3. Ensure the replacement is semantically meaningful and natural
4. Change the question focus in a way that affects the expected answer

For each mapping, provide:
1. question_index: The question number ({question_index})
2. latex_stem_text: Exact LaTeX text of the question stem (must match the input exactly)
3. original_substring: The substring to replace (must be a contiguous substring of latex_stem_text)
4. replacement_substring: The replacement text
5. start_pos: Start position of original_substring relative to latex_stem_text (0-based index)
6. end_pos: End position of original_substring relative to latex_stem_text (exclusive, 0-based index)
7. target_wrong_answer: Description of how the answer should deviate (e.g., "focuses on different aspect", "changes key concept")
8. reasoning: Brief explanation of why this mapping satisfies the strategy and how it causes deviation

IMPORTANT:
- The original_substring MUST be an exact substring of latex_stem_text
- The start_pos and end_pos MUST be accurate (start_pos + len(original_substring) = end_pos)
- The replacement should cause a verifiable deviation in the answer
- CRITICAL: The replacement_substring MUST be DIFFERENT from the original_substring. Do NOT generate mappings where original_substring == replacement_substring. The replacement MUST change the text to create actual manipulation.
- CRITICAL: Neither original_substring nor replacement_substring can be empty strings. Both must contain actual text.
- LENGTH CONSTRAINT: The replacement_substring MUST be smaller or equal in length to the original_substring (len(replacement_substring) <= len(original_substring)). This is critical for maintaining document layout and preventing text overflow.
- latex_stem_text is provided exactly as it appears in the LaTeX source. Do NOT trim, normalise, or reformat it when determining positions.
- The latex_stem_text may include \item tokens from enumerate environments. Keep the \item token intact and operate on the descriptive text that follows it whenever possible.
- The replacement should be natural and semantically meaningful

Return as JSON array:
[
  {{
    "question_index": {question_index},
    "latex_stem_text": "...",
    "original_substring": "...",
    "replacement_substring": "...",
    "start_pos": 0,
    "end_pos": 5,
    "target_wrong_answer": "focuses on different aspect",
    "reasoning": "..."
  }},
  ...
]

Return ONLY valid JSON, no markdown or additional text."""
