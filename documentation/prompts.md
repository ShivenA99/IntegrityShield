# Prompt Catalogue

This catalogue documents the AI prompts used across the simulator. Keep it aligned with the actual strings in code so prompt updates remain auditable.

## OpenAI Vision – Smart Reading

- **Location:** `backend/app/services/ai_clients/openai_vision_client.py`
- **Purpose:** Convert page-level images into structured question JSON during `smart_reading`.
- **System Prompt Summary:** “You are an expert educational assessor…” emphasising accurate transcription and option extraction.
- **User Payload:** Multipart content with the page image (base64) plus instructions to emit JSON (`question_number`, `question_type`, `stem`, `options`, `marks`, `layout`).
- **Parameters:** `temperature=0.0`, `max_tokens=3000`.

## OpenAI Vision – Mapping Geometry

- **Location:** `backend/app/services/pipeline/answer_sheet_generation_service.py` (geometry helper) & future dedicated helpers.
- **Purpose:** Retrieve bounding boxes for specific substrings to anchor replacements.
- **Request Template:**
  ```json
  {
    "task": "Identify the bounding boxes of the specified substrings within the provided question stems.",
    "page": 1,
    "questions": [
      {
        "question_number": "4",
        "stem_text": "If a code block has complexity O(n)...",
        "mappings": [
          {"substring": "complexity O(n)"},
          {"substring": "n times"}
        ]
      }
    ]
  }
  ```
- **Expected Response:** `{ "geometry": [...], "warnings": [] }` with `bbox` arrays in page coordinates.

## GPT-4o Validation

- **Location:** `backend/app/services/validation/gpt5_validation_service.py`
- **Purpose:** Validate manipulated answers against gold answers post-substitution.
- **Prompt Structure:** System prompt declares expert assessor persona; user prompt packages question text, answer choices, gold/manipulated answers, and asks for JSON response with `confidence`, `deviation_score`, `analysis`.
- **Parameters:** `temperature=0.1`, `max_tokens=1500`.

## Multi-Model Effectiveness Testing

- **Location:** `backend/app/services/intelligence/multi_model_tester.py`
- **Purpose:** Replay manipulated questions across configured models (GPT, Claude, Gemini). Each client uses its own prompt template emphasising exam integrity and direct answer output.
- **Notes:** Extend the model strategy map when introducing new LLMs; document prompt changes here.

## Mistral OCR

- **Location:** `backend/app/services/ai_clients/mistral_ocr_client.py`
- **Purpose:** OCR fallback for PDFs; promptless document-to-text pipeline using `pixtral-12b-2409`.
- **Supplemental Prompt:** When requesting structured extraction, we send a JSON instruction emphasising numbering, options, and bounding boxes.

## Classroom Simulation (Subjective Answers)

- **Location:** `AnswerSheetGenerationService._subjective_llm_settings`
- **Purpose:** Optionally call a higher-fidelity model for subjective answers during dataset generation.
- **Configuration:** Driven by `ANSWER_SHEET_DEFAULTS["subjective_llm"]` (model name, temperature, max tokens).
- **Prompt Template:** Lives alongside the generation logic; highlight empathy for cheating strategies while producing plausible text.

## Prompt Governance

- When editing prompt text in code, update this file in the same commit.
- Keep sample payloads and expected outputs in sync to aid testing.
- Note token/latency implications when prompts grow; log cost metrics via `ai_model_results` or stage logs for visibility.
