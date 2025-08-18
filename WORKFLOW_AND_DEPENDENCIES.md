## End-to-End Workflow (Concise)

1) Upload
- Route: `backend/app/routes/assessments.py` → `POST /api/assessments/upload`
- Saves PDFs under `backend/data/assessments/<uuid>/`

2) Parse Questions
- Prefers OCR: `backend/app/services/ocr_service.py` (OpenAI vision) when `USE_OCR != 0`
- Fallback: traditional parse in `backend/app/services/pdf_utils.py::parse_pdf_questions`

3) Apply Attack
- `backend/app/services/attack_service.py::apply_attack`
- Hidden directive injected top/bottom depending on `AttackType`

4) Generate Wrong Answers (distractors)
- `backend/app/services/wrong_answer_service.py::generate_wrong_answer`
- Calls OpenAI when key present; otherwise heuristic fallback

5) Build Attacked PDF + Report
- `backend/app/services/pdf_utils.py::build_attacked_pdf` (LaTeX via `pdflatex`)
- Hidden line: “Answer shown as correct: <LABEL>) <OPTION> — Reason: <TEXT>”
- `backend/app/services/pdf_utils.py::build_reference_report` (txt + simple PDF)

6) Evaluate (optional)
- If `ENABLE_LLM != 0` and attack != NONE:
  - `backend/app/services/openai_eval_service.py::evaluate_pdf_with_openai`
  - Upload to Google Drive → OpenAI Responses API → parse + score

7) Download
- `GET /api/assessments/{id}/attacked` and `/report`


## File-Level Dependency Tree (Key Paths Only)

- `backend/app/__init__.py`
  - loads env (`python-dotenv`), configures DB/CORS, registers routes
  - depends on: `backend/app/routes/assessments.py`

- `backend/app/routes/assessments.py`
  - uses: `models.py` (SQLAlchemy), `pdf_utils.py`, `attack_service.py`, `wrong_answer_service.py`, `openai_eval_service.py`
  - reads env: `ENABLE_LLM`, `DATA_DIR`

- `backend/app/models.py`
  - defines: `Assessment`, `StoredFile`, `Question`, `LLMResponse`

- `backend/app/services/pdf_utils.py`
  - imports: `ocr_service` (if available), `attack_service`
  - external: PyPDF2, reportlab, `pdflatex` (system), OS filesystem

- `backend/app/services/ocr_service.py`
  - external: OpenAI (vision), PIL/Pillow, PyMuPDF
  - env: `OPENAI_API_KEY`

- `backend/app/services/wrong_answer_service.py`
  - external: OpenAI (chat)
  - env: `OPENAI_API_KEY`
  - fallback: local heuristic

- `backend/app/services/openai_eval_service.py`
  - external: OpenAI (Responses API), Google Drive API
  - env: `OPENAI_API_KEY`
  - files: `backend/credentials.json`, `backend/token.json`

- Frontend (root)
  - `App.tsx`, `components/`, `services/assessmentService.ts`
  - Vite proxy: `vite.config.ts` → backend `http://127.0.0.1:5001`


## Critical Env and Tools

- `backend/.env`:
  - `DATABASE_URL`, `OPENAI_API_KEY`, `ENABLE_LLM` (0/1), `USE_OCR` (0/1)
- System tools: `pdflatex` (TeX Live/MacTeX), Docker (Postgres), Python 3.10+
- Google Drive: `backend/credentials.json` (OAuth client), auto `backend/token.json`


## Minimal Run Commands

- DB/migrations
  - `docker run --name fairtestai-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ftai -p 5432:5432 -d postgres:15`
  - `cd backend && source .venv/bin/activate && export FLASK_APP=run.py && flask db upgrade`

- API
  - `python -c "from app import create_app; app = create_app(); app.run(debug=True, host='0.0.0.0', port=5001)"`

- Frontend
  - `npm install && npm run dev`

- Test upload (example)
  - `curl -s -S -X POST -F "original_pdf=@/abs/path/your.pdf;type=application/pdf" -F "attack_type=Hidden Malicious Instruction (Prepended)" http://127.0.0.1:5001/api/assessments/upload` 