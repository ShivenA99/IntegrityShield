# Claude Code Quick-Start Prompt

**Copy-paste this entire message into a new Claude Code session to continue work:**

---

I'm working on **FairTestAI**, an LLM Assessment Vulnerability Simulator on branch `eacl-demo`. Here's what you need to know:

## Current State
- **Working Directory**: `/Users/shivenagarwal/Downloads/fairtestai_-llm-assessment-vulnerability-simulator-main`
- **Branch**: `eacl-demo`
- **Server**: Runs on port 8000 via `backend/scripts/run_dev_server.sh`
- **Database**: SQLite at `backend/data/fairtestai.db`

## Recent Work Context

### ✅ COMPLETED
1. **Font optimization attempt** - Tried to reduce prevention mode font generation from 1,182 to 310 fonts by limiting character variants to 5. Code exists in `app/services/pipeline/latex_font_attack_service.py:503-551` but doesn't work due to cache key uniqueness. **ABANDONED** per user request.

2. **Database migration** - Added `display_name` field to `enhanced_pdfs` table for user-friendly variant names ("Detection 1-5", "Prevention 1-3"). Field added but population/UI not implemented.

3. **Detection mode E2E test** - Successfully ran `backend/test_detection_flow_e2e.py`, generated 5 PDFs + reports.

### 🔄 IN PROGRESS
1. **Prevention mode E2E testing** - Need to run `backend/test_prevention_flow.py` and verify it generates 3 PDFs + reports
2. **Compare detection vs prevention outputs** - Document differences and validate behavior

## How to Run Tests

### Start Server
```bash
cd backend
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false bash scripts/run_dev_server.sh
```

### Run Detection Test
```bash
cd backend
PYTHONUNBUFFERED=1 .venv/bin/python test_detection_flow_e2e.py 2>&1 | tee DETECTION_E2E.log
```
- Takes ~10-15 minutes
- Generates 5 PDFs in `data/pipeline_runs/<RUN_ID>/`
- Creates vulnerability + evaluation reports

### Run Prevention Test
```bash
cd backend
PYTHONUNBUFFERED=1 .venv/bin/python test_prevention_flow.py 2>&1 | tee PREVENTION_E2E.log
```
- Takes ~10-15 minutes
- Generates 3 PDFs in `data/pipeline_runs/<RUN_ID>/`
- Creates vulnerability + evaluation reports
- **NOTE**: Generates 1,000+ fonts (not optimized - this is expected)

### Monitor Progress
```bash
# Get RUN_ID from test output, then:
ls -la data/pipeline_runs/<RUN_ID>/
watch -n 5 "ls -lh data/pipeline_runs/<RUN_ID>/*.pdf"
```

## Key Files

### Pipeline Services
- `app/services/pipeline/latex_font_attack_service.py` - Main attack service, contains optimization code (lines 503-551)
- `app/services/pipeline/font_attack/font_builder.py` - Font building and caching (lines 128-133: cache key generation)
- `app/models/pipeline.py` - Database models (line 136: display_name field)

### Tests
- `backend/test_detection_flow_e2e.py` - Detection mode E2E test (7 stages, 5 variants)
- `backend/test_prevention_flow.py` - Prevention mode E2E test (5 stages, 3 variants)

## Known Issues

1. **Font optimization doesn't work** - Code exists but cache keys are still unique due to `visual_text` field. Abandoned for now.

2. **Python import cache** - If code changes don't take effect:
   ```bash
   lsof -ti:8000 | xargs kill -9
   find app -name "*.pyc" -delete
   find app -name "__pycache__" -type d -exec rm -rf {} +
   ```

3. **Test script API 404s** - Test scripts get 404 errors on status checks (wrong endpoint format), but pipeline runs fine. Ignore these errors, monitor via filesystem instead.

4. **Empty PDF files** - Some generated PDFs are 0 bytes (e.g., `enhanced_latex_icw_font_attack.pdf`). Need to investigate.

## Important Context About Reports
**Both detection and prevention modes generate reports:**
- Vulnerability Report: Same format for both modes
- Evaluation Report: Slightly different content between modes

## What to Do Next

1. **Run prevention mode E2E test** - Execute `test_prevention_flow.py` and verify it completes successfully
2. **Compare outputs** - Check detection vs prevention PDFs and reports, document differences
3. **Investigate 0-byte PDFs** - Determine why some PDFs are empty
4. **(Optional) UI variant naming** - Implement display_name population and UI display

## Additional Context
See `HANDOFF_CONTEXT.md` in the project root for comprehensive details including:
- Detailed technical architecture
- Complete debugging guide
- Pipeline stage dependencies
- Font cache mechanism explanation
- Full file listing and code locations

---

**Questions to ask me:**
- "Show me the current server status"
- "Run the prevention mode test"
- "Compare detection vs prevention outputs"
- "Investigate the empty PDF issue"
- "Help me understand the font caching mechanism"
