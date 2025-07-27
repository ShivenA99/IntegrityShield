
This contains everything you need to run your app locally.

## Features

- **PDF Attack Simulation**: Upload question papers and generate attacked versions with malicious instructions
- **OpenAI Evaluation**: Automatically evaluate attacked PDFs using OpenAI's GPT-4o vision model
- **Attack Success Analysis**: Calculate success rates of prompt injection attacks
- **Multi-format Support**: Works with various PDF formats and question types

## Run Locally

**Prerequisites:**  Node.js, Python 3.8+, PostgreSQL


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Set up the backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   export OPENAI_API_KEY=your_openai_api_key_here
   python3 -m flask db upgrade
   python3 run.py
   ```
4. Run the frontend:
   `npm run dev`

---

## Troubleshooting

### OpenAI API Unauthorized (401)
If you see errors like:
```
HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 401 Unauthorized"
```
- Make sure you have a valid OpenAI API key.
- Set it in your environment or in a `.env` file in the backend directory:
  ```
  OPENAI_API_KEY=sk-...
  ```
- Or, export it in your shell before running Flask:
  ```
  export OPENAI_API_KEY=sk-...
  ```
- Restart your Flask server after setting the key.

### pdflatex Not Found
If you see errors like:
```
RuntimeError: pdflatex executable not found on PATH – install a LaTeX distribution (e.g. TeX Live or MacTeX).
```
- Install a LaTeX distribution that includes `pdflatex`.
- On macOS, the recommended way is to install MacTeX:
  - Download from: https://tug.org/mactex/
  - Or, if you use Homebrew:
    ```
    brew install --cask mactex
    ```
- After installation, add the TeX binaries to your PATH. For MacTeX, add this to your `.zshrc` or `.bash_profile`:
  ```
  export PATH="/Library/TeX/texbin:$PATH"
  ```
- Restart your terminal or run `source ~/.zshrc` (or `source ~/.bash_profile`).
