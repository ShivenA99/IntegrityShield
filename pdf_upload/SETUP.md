# Quick Setup Guide

## 1. Install Dependencies

```bash
cd pdf_upload
pip install -r requirements.txt
```

## 2. Set Up API Keys

Create a `.env` file in the `pdf_upload` directory with your API keys:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key-here
GOOGLE_API_KEY=your-google-api-key-here
```

**Note:** You can get API keys from:
- OpenAI: https://platform.openai.com/api-keys
- Anthropic: https://console.anthropic.com/
- Google: https://makersuite.google.com/app/apikey

## 3. Add PDF Files

Place your PDF files in the `input/` folder:

```bash
cp your_file.pdf input/
```

## 4. Configure Questions (Optional)

Edit `pdf_llm_processor.py` and modify the `questions` list in the `main()` function:

```python
questions = [
    {"qid": 1, "q": "Your question 1"},
    {"qid": 2, "q": "Your question 2"},
    # Add more questions
]
```

## 5. Run the Script

```bash
python pdf_llm_processor.py <pdf_filename>
```

**Example:**
```bash
python pdf_llm_processor.py science_k-12_doc_01.pdf
```

The script will create an output folder with the results:
- `output/<pdf_name>_<timestamp>/results.json`
- `output/<pdf_name>_<timestamp>/report.txt`

## Output Files

- `results.json` - Structured JSON with all responses
- `report.txt` - Human-readable report

## Troubleshooting

- **No API keys found**: Make sure your `.env` file is in the `pdf_upload` directory
- **PDF upload fails**: Check file size (max 50MB by default) and API key validity
- **Import errors**: Make sure all dependencies are installed: `pip install -r requirements.txt`

