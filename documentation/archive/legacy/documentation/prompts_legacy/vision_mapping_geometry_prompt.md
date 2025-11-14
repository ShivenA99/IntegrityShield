# OpenAI Vision – Mapping Geometry Prompt

**Purpose:** After GPT-generated mappings are stored, we re-query OpenAI Vision to obtain bounding boxes for the specific substring being replaced. Those boxes let us deterministically map the substring to PyMuPDF span ids.

**Endpoint:** OpenAI Vision (same as Smart Reading).

**Sample Prompt Payload (per page):**

```json
{
  "task": "Identify the bounding boxes of the specified substrings within the provided question stems.",
  "page": 1,
  "questions": [
    {
      "question_number": "4",
      "stem_text": "If a code block has complexity O(n) and is executed inside another loop that also runs n times, which might correctly describe the overall complexity?",
      "mappings": [
        {"substring": "complexity O(n)"},
        {"substring": "n times"}
      ]
    },
    {
      "question_number": "5",
      "stem_text": "Considering average-case time complexity, which of these statements might be true?",
      "mappings": [
        {"substring": "average-case time complexity"}
      ]
    }
  ]
}
```

**Expected Response:**

```json
{
  "geometry": [
    {
      "question_number": "4",
      "substring": "complexity O(n)",
      "bbox": [x0, y0, x1, y1]
    },
    {
      "question_number": "4",
      "substring": "n times",
      "bbox": [x0, y0, x1, y1]
    },
    {
      "question_number": "5",
      "substring": "average-case time complexity",
      "bbox": [x0, y0, x1, y1]
    }
  ],
  "warnings": []
}
```

**Notes:**
- The page image is the same base64 payload captured during Smart Reading.
- Vision should return bounding boxes relative to the page coordinate system (same as the initial extraction).
- If a substring cannot be located, include an entry in `warnings` explaining why (e.g., substring not present, OCR limitations).
- After receiving the bbox, we expand it slightly (±8–10 pt) to capture all spans, then map those spans back to PyMuPDF span ids.
