# PDF LLM Processor - Implementation Documentation

## Overview

The PDF LLM Processor is a Python application that uploads PDF documents to multiple LLM providers (Anthropic Claude and OpenAI GPT) and queries them to answer questions found within the PDFs. The system processes assessment PDFs that contain questions and extracts answers from both LLM providers in parallel.

## Architecture

### Core Components

1. **PDFLLMProcessor** (`pdf_llm_processor.py`)
   - Main orchestrator that coordinates PDF upload, LLM queries, and result processing
   - Handles configuration loading, client initialization, and result structuring

2. **LLM Clients** (`llm_clients.py`)
   - `AnthropicClient`: Uses Anthropic Files API for PDF upload and querying
   - `OpenAIClient`: Uses OpenAI Files API with combined upload+query approach
   - Each client handles provider-specific API formats and error handling

3. **Report Generator** (`report_generator.py`)
   - Formats and generates human-readable reports from structured JSON results

## How It Works

### Workflow

```
1. Initialize Clients
   ├── Load configuration (config.yaml)
   ├── Initialize Anthropic client (if API key available)
   └── Initialize OpenAI client (if API key available)

2. Upload PDF
   ├── Anthropic: Upload to Files API → Get file_id
   └── OpenAI: Prepare for combined upload+query

3. Query LLMs (Parallel)
   ├── Anthropic: Query with file_id using Files API
   └── OpenAI: Upload + Query in single method call

4. Parse Responses
   ├── Extract JSON from LLM responses
   ├── Parse questions and answers
   └── Merge results from both providers

5. Structure Results
   ├── Group by question ID
   ├── Combine answers from all LLMs
   └── Generate JSON output

6. Generate Report
   └── Create formatted text report
```

### Key Design Decisions

1. **Combined Upload+Query for OpenAI**: OpenAI's upload and query are combined in a single method call to ensure the PDF and prompt are sent together, avoiding issues with separate steps.

2. **Files API for Anthropic**: Uses Anthropic's Files API (beta) instead of base64 encoding for better efficiency and file persistence.

3. **Parallel Processing**: Both LLMs are queried in parallel using `asyncio.gather()` for optimal performance.

4. **Single Call per LLM**: One API call per LLM that answers all questions in the PDF, rather than multiple calls per question.

## Configuration

### config.yaml

```yaml
api_keys:
  anthropic: "${ANTHROPIC_API_KEY}"  # From environment
  openai: "${OPENAI_API_KEY}"        # From environment

models:
  anthropic: "claude-sonnet-4-5-20250929"
  openai: "gpt-5.1"

prompt: "Answer the questions"

pdf_settings:
  input_folder: "input"
  max_file_size_mb: 50

retry_settings:
  max_retries: 3
  retry_delay: 2
  timeout: 60
```

### Environment Variables

Required environment variables:
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `OPENAI_API_KEY`: Your OpenAI API key

## API Implementation Details

### Anthropic Client

**Upload Method:**
- Endpoint: `POST /v1/files`
- Headers: `anthropic-beta: files-api-2025-04-14`
- Returns: `file_id` for use in queries

**Query Method:**
- Endpoint: `POST /v1/messages`
- Content Structure:
  ```json
  {
    "content": [
      {
        "type": "text",
        "text": "prompt text"
      },
      {
        "type": "document",
        "source": {
          "type": "file",
          "file_id": "file_xxx"
        }
      }
    ]
  }
  ```

### OpenAI Client

**Combined Upload+Query:**
- Upload: `POST /v1/files` with `purpose="user_data"`
- Wait for file processing (status: "processed")
- Query: `POST /v1/chat/completions` with:
  ```json
  {
    "content": [
      {
        "type": "file",
        "file": {
          "file_id": "file-xxx"
        }
      },
      {
        "type": "text",
        "text": "prompt text"
      }
    ]
  }
  ```

## Code Structure

### Main Entry Point

```python
python pdf_llm_processor.py <pdf_filename>
```

### Key Methods

#### PDFLLMProcessor

- `_initialize_clients()`: Initializes Anthropic and OpenAI clients
- `upload_pdf()`: Uploads PDF to all available providers
- `query_llm()`: Queries a specific LLM with all questions
- `process_pdf()`: Main processing pipeline
- `_parse_llm_response()`: Extracts JSON from LLM responses
- `generate_report()`: Creates formatted report

#### AnthropicClient

- `upload_file()`: Uploads PDF to Files API
- `query_with_file()`: Queries with file_id

#### OpenAIClient

- `upload_file()`: Returns PDF path (no-op, upload happens in query)
- `query_with_file()`: Combined upload + query + wait for processing

## Output Format

### JSON Structure

```json
{
  "document": {
    "type": "document",
    "id": "timestamp",
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
            "answer": "Answer text",
            "success": true
          },
          {
            "model_name": "OPENAI",
            "prompt": "Answer the questions",
            "answer": "Answer text",
            "success": true
          }
        ]
      }
    ]
  }
}
```

### Report Format

The report generator creates a text file with:
- Document metadata
- Questions grouped by ID
- Answers from all LLMs side-by-side
- Success/error indicators

## Error Handling

### Retry Logic

- Maximum retries: 3 (configurable)
- Exponential backoff: `delay = retry_delay * (attempt + 1)`
- Applied per LLM query

### Error Types

1. **Upload Errors**: File not found, upload failed, processing timeout
2. **Query Errors**: API errors, rate limits, empty responses
3. **Parsing Errors**: Invalid JSON, missing fields

### Error Response Format

```json
{
  "model_name": "OPENAI",
  "prompt": "Answer the questions",
  "answer": null,
  "error": "Error message",
  "success": false
}
```

## Dependencies

### Required Packages

```
aiohttp          # Async HTTP client
pyyaml           # YAML configuration parsing
python-dotenv    # Environment variable loading
```

### Optional Packages

```
openai           # OpenAI SDK (fallback if available)
certifi          # SSL certificate handling
```

## Usage Examples

### Basic Usage

```bash
# Set environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# Run processor
python pdf_llm_processor.py science_k-12_doc_01.pdf
```

### Output Location

Results are saved to:
```
output/<pdf_name>_<timestamp>/
├── results.json    # Structured JSON with all Q&A
└── report.txt      # Human-readable report
```

## Performance Considerations

1. **Parallel Processing**: Both LLMs query in parallel, reducing total time
2. **Single Call per LLM**: One API call answers all questions (more efficient than N calls)
3. **File Processing Wait**: OpenAI requires waiting for file processing (adds ~2-10 seconds)
4. **Timeout Settings**: 120 seconds for API calls, 60 seconds for file processing

## Limitations

1. **PDF Size**: Limited by provider limits (OpenAI: varies, Anthropic: 500MB max)
2. **Question Extraction**: Relies on LLM to identify and extract questions from PDF
3. **JSON Parsing**: Requires LLM to format response as JSON (fallback to full text if parsing fails)
4. **Rate Limits**: Subject to provider rate limits (100 req/min for Anthropic Files API during beta)

## Future Improvements

1. **Question Extraction**: Pre-extract questions from PDF using OCR/parsing
2. **Caching**: Cache uploaded files to avoid re-uploading
3. **Streaming**: Support streaming responses for long documents
4. **Batch Processing**: Process multiple PDFs in batch
5. **Metadata Extraction**: Auto-populate `asses_details` from PDF content

## Troubleshooting

### No OpenAI Results

- Check API key is set correctly
- Verify file upload succeeded (check console output)
- Ensure file processing completed (status: "processed")
- Check error messages in console output

### No Anthropic Results

- Verify Files API beta header is included
- Check file_id is valid
- Ensure model supports Files API (Claude 3.5+)

### JSON Parsing Errors

- LLM may not have formatted response as JSON
- Check response preview in console output
- System falls back to using full response as single answer

## API Reference

### PDFLLMProcessor Class

```python
class PDFLLMProcessor:
    def __init__(config_path: str = "config.yaml")
    async def upload_pdf(pdf_path: str) -> Dict[str, Optional[str]]
    async def query_llm(client_name: str, file_id: str, prompt: str) -> dict
    async def process_pdf(pdf_path: str) -> dict
    def generate_report(results: dict, output_path: str)
```

### AnthropicClient Class

```python
class AnthropicClient:
    async def upload_file(pdf_path: str) -> str
    async def query_with_file(file_id: str, prompt: str, question_data: Optional[dict] = None) -> str
```

### OpenAIClient Class

```python
class OpenAIClient:
    async def upload_file(pdf_path: str) -> str
    async def query_with_file(file_id: str, prompt: str, question_data: Optional[dict] = None) -> str
```

## License

[Add your license information here]

## Author

[Add author information here]

