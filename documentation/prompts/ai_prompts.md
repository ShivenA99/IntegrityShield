# AI Prompt Catalog

This document catalogs the prompts used when calling external AI services. Update it whenever prompt wording or parameters change.

## GPT-5 Fusion (OpenAI `gpt-4o`)

### Question Analysis Prompt
- **Location:** `backend/app/services/ai_clients/gpt5_fusion_client.py::_create_question_analysis_prompt`
- **Use Case:** Analyze PyMuPDF text elements to identify questions and manipulation targets.
- **System Prompt:** “You are an expert at analyzing academic assessment documents…”
- **User Prompt Content:**
  - Sorted list of text spans with bounding boxes.
  - Request to identify questions, classify them, and propose manipulation targets.
- **Parameters:** `temperature=0.1`, `max_tokens=4000`.

### Fusion Prompt
- **Location:** `gpt5_fusion_client.py::_create_fusion_prompt`
- **System Prompt:** “You are an expert AI system that intelligently merges question extraction results from multiple sources to produce the most accurate final output.”
- **User Prompt Content:**
  - PyMuPDF `content_elements` JSON.
  - OpenAI Vision results (structured questions + confidence).
  - Mistral OCR markdown/annotations.
  - Instructions to return a JSON object containing fusion analysis + final question list (see code for exact template).
- **Parameters:** `temperature=0.0`, `max_tokens=6000`.

## GPT-5 Validation (OpenAI `gpt-4o`)

- **Location:** `backend/app/services/validation/gpt5_validation_service.py`
- **System Prompt:** “You are an expert educational assessment validator…”
- **User Prompt:** Dynamically built string containing:
  - Question text and type.
  - Gold answer and test answer.
  - Optional options list.
  - Question-type-specific instructions (e.g. MCQ vs short answer).
  - Analysis framework and requested JSON schema for the response (confidence, deviation score, reasoning, etc.).
- **Parameters:** `temperature=0.1`, `max_tokens=1500`.

## Mistral OCR

### Document OCR
- **Location:** `backend/app/services/ai_clients/mistral_ocr_client.py`
- **Prompt:** API is document-first; no explicit prompt when using `client.ocr.process`. Returns structured JSON with per-page markdown.

### Page-Level Extraction
- **Location:** `MistralOCRClient::_create_question_extraction_prompt`
- **Prompt Summary:** Instructions for extracting questions from a page image with precise numbering, options, and bounding boxes. Prompt requests JSON-formatted output.
- **Parameters:** Default model `pixtral-12b-2409`, `temperature` default per SDK.

## OpenAI Vision (Image to Text)

- **Location:** `backend/app/services/ai_clients/openai_vision_client.py`
- **System Prompt:** “You are an expert educational assessor…” (see file for full text).
- **User Prompt:** Provides base64-encoded page image + instructions to output questions as JSON (question number, type, stem, options, positioning).
- **Parameters:** `temperature=0.0`, `max_tokens=3000`.

## Multi-Model Tester

- **Location:** `backend/app/services/intelligence/multi_model_tester.py`
- **Prompts:** Each configured model may have its own template (e.g., GPT, Claude). Document these as we integrate additional models.

## Maintaining Prompts
- Keep prompt text close to the calling code for version control.
- When updating prompts, note changes here (especially if output schema changes).
- Track token usage/cost via logs (`cost_cents` fields) to monitor impact of prompt length.
