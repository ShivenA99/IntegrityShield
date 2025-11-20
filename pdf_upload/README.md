# PDF LLM Processor

A Python tool that uploads PDFs to multiple LLM providers (OpenAI GPT-5.1 and Anthropic Claude) and queries them to answer questions found within assessment PDFs. The system processes PDFs that contain questions and extracts answers from both LLM providers in parallel.

## Features

- 📤 Direct PDF upload to OpenAI and Anthropic using their Files APIs
- 🔄 Parallel API calls for efficient processing
- 🔁 Automatic retry with exponential backoff
- ⚙️ Configuration-based setup (YAML)
- 📊 Structured JSON output with answers from both LLMs
- 📝 Formatted report generation
- 🎯 Single API call per LLM that answers all questions in the PDF

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys:**
   - Create a `.env` file or export environment variables:
     ```
     OPENAI_API_KEY=sk-...
     ANTHROPIC_API_KEY=sk-ant-...
     ```
   - At least one API key is required (both recommended for comparison)

3. **Add PDF files:**
   - Place your PDF files in the `input/` folder

4. **Configure prompts and settings:**
   - Edit `config.yaml` to customize prompts, models, and other settings

## Usage

Run the main script with a PDF filename as argument:

```bash
python pdf_llm_processor.py <pdf_filename>
```

**Example:**
```bash
python pdf_llm_processor.py science_k-12_doc_01.pdf
```

**With custom output directory:**
```bash
python pdf_llm_processor.py science_k-12_doc_01.pdf --output-dir my_output
```

The script will:
1. Look for the specified PDF file in the `input/` folder
2. Upload PDF to all configured LLM providers (Anthropic and OpenAI)
3. Make 1 API call per LLM to answer all questions in the PDF
4. Parse responses and merge answers from both LLMs
5. Create an output folder: `output/<pdf_name>_<timestamp>/`
6. Generate structured JSON results (`results.json`) with answers from both LLMs
7. Generate a formatted report (`report.txt`) in the output folder

**Output Structure:**
```
output/
  └── science_k-12_doc_01_20250114_120000/
      ├── results.json
      └── report.txt
```

## Configuration

Edit `config.yaml` to customize:

- **API Keys**: Set via environment variables (see `.env`)
- **Models**: Choose specific model versions
- **Prompts**: Customize the prompts used for queries
- **Retry Settings**: Configure retry attempts and delays
- **PDF Settings**: Input folder and file size limits

## Output Format

### JSON Results (`results.json`)

```json
{
  "document": {
    "type": "document",
    "id": "20250101_120000",
    "asses_details": {
      "sub": "",
      "dom": ""
    }
  },
  "questions": {
    "type": "questions",
    "items": [
      {
        "qid": 1,
        "q": "Question text",
        "answers": [
          {
            "model_name": "ANTHROPIC",
            "prompt": "Answer the questions",
            "answer": "Response text",
            "success": true
          },
          {
            "model_name": "OPENAI",
            "prompt": "Answer the questions",
            "answer": "Response text",
            "success": true
          }
        ]
      }
    ]
  }
}
```

### Report (`report.txt`)

A human-readable report with:
- Assessment details
- Question-wise breakdown
- Responses from each LLM provider

## Troubleshooting

- **No API keys found**: Make sure your `.env` file is in the `pdf_upload` directory, or export them as environment variables
- **PDF upload fails**: Check file size (max 50MB by default) and API key validity
- **No results from a provider**: Check console output for error messages; verify API keys are valid
- **SSL Certificate errors**: The script uses `certifi` for SSL certificate verification. Install it with: `pip install certifi`
- **Import errors**: Make sure all dependencies are installed: `pip install -r requirements.txt`

## Implementation Details

- **Single Call per LLM**: One API call per LLM answers all questions in the PDF (more efficient)
- **Parallel Processing**: Both LLMs are queried in parallel for optimal performance
- **Combined Upload+Query for OpenAI**: PDF upload and query are combined in one method call
- **Files API for Anthropic**: Uses Anthropic's Files API (beta) for efficient file handling
- **Automatic Retry**: Failed calls are retried with exponential backoff (3 retries by default)
- **Graceful Degradation**: If a provider's API key is missing, that provider is skipped
- **JSON Response Parsing**: LLMs are asked to format responses as JSON for structured extraction

## Technical Details

- **Anthropic**: Uses Files API (`anthropic-beta: files-api-2025-04-14`) with file_id references
- **OpenAI**: Uses Files API with `purpose="user_data"` and combined upload+query approach
- **Models**: GPT-5.1 (OpenAI) and Claude Sonnet 4.5 (Anthropic)
- **SSL**: Uses `certifi` for SSL certificate verification on macOS

For detailed implementation documentation, see [IMPLEMENTATION.md](IMPLEMENTATION.md).

