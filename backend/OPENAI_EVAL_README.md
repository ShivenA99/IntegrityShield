# OpenAI PDF Evaluation Service

This document describes the new OpenAI-based PDF evaluation functionality that uploads entire PDFs to OpenAI and evaluates if the AI's answers match the malicious ones.

## Overview

Instead of evaluating questions individually, the new system:
1. Uploads the entire attacked PDF to OpenAI's GPT-4o vision model
2. Asks the AI to answer all questions in the document
3. Compares the AI's answers with both correct and malicious answers
4. Calculates the success rate of the attack

## Key Features

- **PDF Upload**: Encodes PDF files to base64 and sends them to OpenAI's vision API
- **Bulk Evaluation**: Evaluates all questions in a document at once
- **Attack Success Calculation**: Determines if the AI was influenced by malicious instructions
- **Detailed Analysis**: Provides per-question breakdown of results

## API Endpoints

### Automatic Evaluation
When uploading an assessment, if `ENABLE_LLM=1` and an attack type is selected, the system will automatically evaluate the attacked PDF.

### Manual Evaluation
```
POST /api/assessments/{assessment_id}/evaluate
```

Triggers evaluation of an existing assessment.

## Database Changes

The `Question` model now includes:
- `wrong_answer`: The malicious answer generated for this question
- `wrong_reason`: The reasoning behind the malicious answer

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: Required for OpenAI API access
- `OPENAI_EVAL_MODEL`: Model to use (default: "gpt-4o-mini")
- `ENABLE_LLM`: Set to "0" to disable LLM evaluation

### Model Selection
- For PDF analysis: Uses `gpt-4o` (vision model)
- For text processing: Uses `gpt-4o-mini` (faster, cheaper)

## Usage Example

```python
from app.services.openai_eval_service import evaluate_pdf_with_openai

# Evaluate a PDF
results = evaluate_pdf_with_openai(
    attacked_pdf_path=Path("path/to/attacked.pdf"),
    reference_answers={1: "A", 2: "B", 3: "C"},
    malicious_answers={1: "C", 2: "D", 3: "A"}
)

print(f"Attack success rate: {results['success_rate']:.1f}%")
```

## Response Format

```json
{
  "assessment_id": "uuid",
  "evaluation": {
    "ai_answers": {"1": "C", "2": "D", "3": "A"},
    "reference_answers": {"1": "A", "2": "B", "3": "C"},
    "malicious_answers": {"1": "C", "2": "D", "3": "A"},
    "evaluation": {
      "1": {
        "ai_answer": "C",
        "reference_answer": "A",
        "malicious_answer": "C",
        "chose_malicious": true,
        "chose_correct": false,
        "influenced": true,
        "attack_successful": true
      }
    },
    "success_rate": 100.0
  }
}
```

## Testing

Run the test script to verify functionality:
```bash
cd backend
python3 test_openai_eval.py
```

## Error Handling

- Missing OpenAI API key: Returns error with clear message
- PDF encoding failures: Logs error and raises exception
- API call failures: Attempts fallback to legacy client
- Parsing failures: Logs warning and continues with available data

## Security Considerations

- PDFs are encoded to base64 and sent to OpenAI
- No PDF data is stored permanently in OpenAI's systems
- API responses are logged for debugging but not stored long-term
- Environment variables should be properly secured

## Performance Notes

- PDF encoding can be slow for large files
- OpenAI API calls have rate limits and costs
- Vision model responses are slower than text-only models
- Consider caching results for repeated evaluations 