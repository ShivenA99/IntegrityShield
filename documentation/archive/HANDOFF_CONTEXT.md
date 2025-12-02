# FairTestAI - Comprehensive Project Handoff

## 📋 Project Overview

**FairTestAI** is an LLM Assessment Vulnerability Simulator that identifies and demonstrates vulnerabilities in LLM-based assessment systems. The platform processes educational PDFs and applies various LaTeX-based attacks to test whether LLMs can be manipulated during assessment grading.

### Key Concepts
- **Detection Mode**: Runs 7 pipeline stages to identify vulnerabilities using 5 different LaTeX attack methods
- **Prevention Mode**: Runs 5 pipeline stages (skips smart_substitution & effectiveness_testing) to proactively defend against attacks using 3 prevention methods
- **Pipeline Stages**: smart_reading → content_discovery → smart_substitution → effectiveness_testing → document_enhancement → pdf_creation → results_generation

## 🌲 Current Branch & State

**Branch**: `eacl-demo`
**Working Directory**: `/Users/shivenagarwal/Downloads/fairtestai_-llm-assessment-vulnerability-simulator-main`

### Modified Files (Not Committed)
- `backend/TEST_RESULTS.md` - Test execution logs
- `backend/data/fairtestai.db-*` - Database files (SQLite WAL mode)
- `backend/test_llm_api_mocks_simple.py`
- `backend/test_streamlined_mapping_format.py`
- `backend/test_streamlined_mapping_service.py`

## 🎯 Recent Work Context

### Completed Work
1. ✅ **Font Optimization Attempt** (ABANDONED per user request)
   - Tried to reduce font generation in prevention mode from ~1,182 fonts to ~310 fonts
   - Implemented MAX_VARIANTS=5 optimization in `app/services/pipeline/latex_font_attack_service.py`
   - Issue: Optimization code exists but doesn't reduce font count due to cache key uniqueness
   - Status: User explicitly requested to abandon this and focus on E2E testing instead

2. ✅ **Database Migration for Display Names**
   - Added `display_name` field to `enhanced_pdfs` table
   - Migration: `migrations/versions/9c4d5e6f7g8i_add_display_name_to_enhanced_pdfs.py`
   - Purpose: Show user-friendly variant names ("Detection 1-5", "Prevention 1-3") instead of technical method names
   - Status: Database field added, but population and UI display not yet implemented

3. ✅ **Detection Mode E2E Test** (COMPLETED)
   - Successfully ran full detection pipeline test
   - Test script: `backend/test_detection_flow_e2e.py`
   - Generated 5 enhanced PDFs and reports
   - Run ID: `35a245f1-7a36-4bec-8ea3-ce2dd5b25ea3` (may be cleaned up by now)

### Current Tasks
- 🔄 **Prevention Mode E2E Testing** - Needs to be run/verified
- 📝 **Comprehensive E2E Validation** - Compare detection vs prevention outputs

### Important Context About Reports
**CORRECTION**: Both detection and prevention modes generate reports:
- **Vulnerability Report**: Same format for both modes
- **Evaluation Report**: Slightly different content between modes

## 🗂️ Key Files & Their Purposes

### Core Pipeline Services
```
app/services/pipeline/latex_font_attack_service.py
├── Lines 503-514: Font optimization code (MAX_VARIANTS = 5)
├── Lines 544-551: Cyclic variant selection
├── Line 347: _apply_font_attack() - Detection mode method
├── Line 476: _apply_prevention_font_attack() - Prevention mode method
└── Lines 153-160: Mode detection and branching logic
```

### Font Caching Mechanism
```
app/services/pipeline/font_attack/font_builder.py
├── Lines 50-94: build_fonts() - Main font building with cache lookup
├── Lines 128-133: _derive_cache_key() - SHA-256 hash from hidden_char + visual_text + advance_width
└── Lines 135-154: FontCache class - File-based cache implementation
```

### Database Models
```
app/models/pipeline.py
└── Line 136: display_name field (nullable String(128))
```

### E2E Test Scripts
```
backend/test_detection_flow_e2e.py
├── Tests all 7 detection pipeline stages
├── Uses Mathematics K12 Assessment
├── Expects 5 LaTeX attack variants
└── Auto-generates reports

backend/test_prevention_flow.py
├── Tests 5 prevention pipeline stages
├── Uses Statistics EACL demo dataset
├── Expects 3 prevention variants
└── Generates reports
```

## 🚀 Setup Instructions

### 1. Start the Backend Server
```bash
cd backend
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false bash scripts/run_dev_server.sh
```

**Important Notes:**
- Server runs on port 8000 by default
- Set `FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false` to prevent automatic migrations
- The script activates the virtual environment automatically
- Server logs written to console

### 2. Verify Server is Running
```bash
lsof -ti:8000  # Should return a PID
curl http://localhost:8000/api/health  # Should return 200 OK
```

### 3. Run Database Migrations (if needed)
```bash
cd backend
.venv/bin/flask --app app db upgrade
```

## 🧪 Running E2E Tests

### Detection Mode Test
```bash
cd backend
PYTHONUNBUFFERED=1 .venv/bin/python test_detection_flow_e2e.py 2>&1 | tee DETECTION_E2E.log
```

**Expected Output:**
- Pipeline starts with a run ID
- Monitors 7 stages: smart_reading → content_discovery → smart_substitution → effectiveness_testing → document_enhancement → pdf_creation → results_generation
- Generates 5 enhanced PDFs
- Creates vulnerability report + evaluation report
- Takes ~10-15 minutes

**Test Document:**
- Original PDF: `data/pipeline_runs/245dd78d-7e81-4172-930c-b87ae00a9b32/Mathematics_K12_Assessment.pdf`
- Answer Key: `data/pipeline_runs/245dd78d-7e81-4172-930c-b87ae00a9b32/answer_key_math_answer_key_final.pdf`

### Prevention Mode Test
```bash
cd backend
PYTHONUNBUFFERED=1 .venv/bin/python test_prevention_flow.py 2>&1 | tee PREVENTION_E2E.log
```

**Expected Output:**
- Pipeline starts with a run ID
- Monitors 5 stages (skips smart_substitution & effectiveness_testing)
- Generates 3 prevention-variant PDFs
- Creates vulnerability report + evaluation report
- Takes ~10-15 minutes
- **WARNING**: Generates 1,000+ fonts (not optimized)

**Test Document:**
- Question PDF: `../Eacl_demo_papers/Statistics/qpaper.pdf`
- Answer PDF: `../Eacl_demo_papers/Statistics/answerkey.pdf`
- Question TeX: `../Eacl_demo_papers/Statistics/qpaper.tex`
- Answer TeX: `../Eacl_demo_papers/Statistics/answerkey.tex`

### Monitoring Test Progress

**Via Filesystem** (RECOMMENDED):
```bash
# Get run ID from test output, then:
ls -la data/pipeline_runs/<RUN_ID>/
watch -n 5 "ls -lh data/pipeline_runs/<RUN_ID>/*.pdf"
```

**Via API** (BROKEN - Returns 404):
The test scripts try to use `/api/pipeline/status/{run_id}` but the correct endpoint is `/api/pipeline/{run_id}/status`. This causes 404 errors but doesn't affect pipeline execution.

## ⚠️ Known Issues & Workarounds

### Issue 1: Font Optimization Not Working
**Problem**: Even with MAX_VARIANTS=5 code in place, prevention mode still generates 1,000+ fonts instead of ~310.

**Root Cause**: Font cache keys include `visual_text` which appears to be unique per position, preventing cache hits despite limiting character variants.

**Affected Code**: `app/services/pipeline/latex_font_attack_service.py:503-551`

**Status**: ABANDONED per user request. Not currently being fixed.

**Workaround**: Accept the higher font count for now.

### Issue 2: Python Module Import Cache
**Problem**: When modifying Python files, Flask's auto-reload doesn't always pick up changes.

**Symptoms**: Code changes don't take effect even after saving files.

**Fix**:
```bash
# Kill all servers
lsof -ti:8000 | xargs kill -9

# Clean Python cache
find app -name "*.pyc" -delete
find app -name "__pycache__" -type d -exec rm -rf {} +

# Restart server fresh
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false bash scripts/run_dev_server.sh
```

### Issue 3: Test Script API Endpoint 404s
**Problem**: Test scripts get 404 errors when checking pipeline status.

**Root Cause**: Scripts use wrong endpoint format `/api/pipeline/status/{run_id}` instead of `/api/pipeline/{run_id}/status`.

**Impact**: None - pipeline runs correctly in background despite status check failures.

**Workaround**: Monitor via filesystem instead of API calls.

### Issue 4: Empty PDF Files
**Symptom**: Some enhanced PDFs have 0 bytes (e.g., `enhanced_latex_icw_font_attack.pdf`).

**Status**: Observed in detection mode tests, root cause unknown.

**Action Needed**: Investigate if this is expected or a bug.

## 📊 Expected Test Outputs

### Detection Mode Output Structure
```
data/pipeline_runs/<RUN_ID>/
├── Mathematics_K12_Assessment.pdf (original)
├── answer_key_answer_key_math_answer_key_final.pdf
├── enhanced_latex_dual_layer.pdf (~7 MB)
├── enhanced_latex_font_attack.pdf (~400 KB)
├── enhanced_latex_icw_dual_layer.pdf (~7 MB)
├── enhanced_latex_icw_font_attack.pdf (0 bytes - ISSUE!)
├── enhanced_latex_icw.pdf (~200 KB)
├── detection_report/
│   └── detection_report.json (~26 KB)
├── evaluation_report/
│   └── latex_icw/
│       └── evaluation_report_latex_icw.json
└── artifacts/
    ├── latex-dual-layer/
    ├── latex-font-attack/
    └── latex-icw/
```

### Prevention Mode Output Structure (Expected)
```
data/pipeline_runs/<RUN_ID>/
├── qpaper.pdf (original)
├── answerkey.pdf
├── enhanced_prevention_variant_1.pdf
├── enhanced_prevention_variant_2.pdf
├── enhanced_prevention_variant_3.pdf
├── vulnerability_report/
│   └── vulnerability_report.json
└── evaluation_report/
    └── [prevention-specific evaluation]
```

## 🔍 Verification Checklist

After running tests, verify:

### Detection Mode Checklist
- [ ] Pipeline completed all 7 stages
- [ ] Exactly 5 enhanced PDFs generated (some may be 0 bytes - investigate)
- [ ] Vulnerability report exists (`detection_report/detection_report.json`)
- [ ] Evaluation report exists (at least one in `evaluation_report/`)
- [ ] No errors in server logs
- [ ] PDFs are valid and openable (except 0-byte ones)

### Prevention Mode Checklist
- [ ] Pipeline completed 5 stages (skipped 2)
- [ ] Exactly 3 prevention-variant PDFs generated
- [ ] Vulnerability report exists
- [ ] Evaluation report exists with prevention-specific content
- [ ] Font count is high (~1,000+) - this is expected due to unoptimized code
- [ ] No errors in server logs

## 🎓 Technical Deep Dives

### Font Cache Key Generation
```python
def _derive_cache_key(self, position: AttackPosition) -> str:
    digest = hashlib.sha256()
    digest.update(self.base_font_path.name.encode("utf-8"))
    digest.update(position.hidden_char.encode("utf-8"))  # Single character
    digest.update(position.visual_text.encode("utf-8"))  # May be unique per position!
    digest.update(str(int(round(position.advance_width))).encode("utf-8"))
    return digest.hexdigest()
```

**Key Insight**: Even if we limit `hidden_char` to 5 variants, the `visual_text` field varies per position, creating unique cache keys. This prevents font reuse and explains why optimization didn't work.

### Pipeline Stage Dependencies
```
Detection Mode (7 stages):
smart_reading (extracts questions)
  ↓
content_discovery (finds substitution opportunities)
  ↓
smart_substitution (applies mappings)
  ↓
effectiveness_testing (validates attacks)
  ↓
document_enhancement (optimizes LaTeX, applies 5 methods)
  ↓
pdf_creation (generates final PDFs)
  ↓
results_generation (creates reports)

Prevention Mode (5 stages):
smart_reading
  ↓
content_discovery
  ↓
[SKIPPED: smart_substitution]
  ↓
[SKIPPED: effectiveness_testing]
  ↓
document_enhancement (applies 3 prevention methods)
  ↓
pdf_creation
  ↓
results_generation
```

### Detection vs Prevention Methods
**Detection Methods (5)**:
1. latex_dual_layer
2. latex_font_attack
3. latex_icw_dual_layer
4. latex_icw_font_attack
5. latex_icw

**Prevention Methods (3)**:
- Specific methods TBD - check code in `latex_font_attack_service.py`

## 📝 Next Steps & Recommendations

### Immediate Actions
1. **Run Prevention Mode E2E Test**
   - Execute `test_prevention_flow.py`
   - Monitor for completion (~10-15 minutes)
   - Verify 3 PDFs + reports generated

2. **Compare Detection vs Prevention Outputs**
   - Document differences in PDF generation
   - Compare report structures
   - Validate mode-specific behavior

3. **Investigate 0-Byte PDF Issue**
   - Check why `enhanced_latex_icw_font_attack.pdf` is empty in detection mode
   - Determine if this is expected or a bug
   - Review server logs for errors during generation

### Future Enhancements
1. **Font Optimization** (if resumed)
   - Investigate `visual_text` field generation in `planner.plan()`
   - Consider modifying cache key to exclude or normalize `visual_text`
   - Alternative: Pre-generate font pool and reuse

2. **UI Variant Naming** (partially complete)
   - Implement display_name population logic
   - Update UI to show "Detection 1-5" and "Prevention 1-3"
   - Map technical method names to user-friendly names

3. **Test Script Improvements**
   - Fix API endpoint URLs (status endpoint 404s)
   - Add better error handling
   - Implement retry logic for API calls

## 🔗 Important File Paths

### Backend Code
- **Main service**: `app/services/pipeline/latex_font_attack_service.py`
- **Font builder**: `app/services/pipeline/font_attack/font_builder.py`
- **Font planner**: `app/services/pipeline/font_attack/chunking.py`
- **Pipeline models**: `app/models/pipeline.py`
- **Server runner**: `scripts/run_dev_server.sh`

### Test Files
- **Detection test**: `backend/test_detection_flow_e2e.py`
- **Prevention test**: `backend/test_prevention_flow.py`
- **Other tests**: `backend/test_*.py` (many available)

### Data & Migrations
- **Database**: `backend/data/fairtestai.db`
- **Pipeline runs**: `backend/data/pipeline_runs/<RUN_ID>/`
- **Migrations**: `backend/migrations/versions/`
- **Display name migration**: `9c4d5e6f7g8i_add_display_name_to_enhanced_pdfs.py`

### Configuration
- **CLAUDE.md**: Project instructions (mentions using run.sh with correct env vars)
- **Environment vars**: Set in `scripts/run_dev_server.sh`

## 🐛 Debugging Tips

### Server Won't Start
```bash
# Check if port is in use
lsof -ti:8000

# Kill existing processes
lsof -ti:8000 | xargs kill -9

# Check virtual environment
ls -la .venv/bin/python

# Verify dependencies
.venv/bin/pip list | grep -i flask
```

### Pipeline Stuck or Slow
```bash
# Monitor server logs in real-time
tail -f server.log  # or whatever log file you're using

# Check database for pipeline status
sqlite3 data/fairtestai.db "SELECT run_id, mode, current_stage, status FROM pipeline_runs ORDER BY created_at DESC LIMIT 5;"

# Monitor font generation
watch -n 2 "find data/pipeline_runs/<RUN_ID>/ -name '*.ttf' | wc -l"
```

### Code Changes Not Taking Effect
```bash
# Full cache clear and restart
lsof -ti:8000 | xargs kill -9
find app -name "*.pyc" -delete
find app -name "__pycache__" -type d -exec rm -rf {} +
FAIRTESTAI_AUTO_APPLY_MIGRATIONS=false bash scripts/run_dev_server.sh
```

## 📞 Getting Help

- **GitHub Issues**: https://github.com/anthropics/fairtestai (if public repo)
- **Test Results**: Check `backend/TEST_RESULTS.md` for historical test logs
- **Git History**: Review recent commits on `eacl-demo` branch for context

## 🎯 Success Criteria

Your setup is working correctly when:
1. ✅ Server starts without errors
2. ✅ Detection mode test completes with 5 PDFs + reports
3. ✅ Prevention mode test completes with 3 PDFs + reports
4. ✅ No critical errors in server logs
5. ✅ Generated PDFs are valid and openable (investigate 0-byte files)

---

**Last Updated**: December 1, 2025
**Branch**: `eacl-demo`
**Environment**: macOS (Darwin 24.5.0)
**Python**: 3.9+ (in .venv)
**Flask**: Development server on port 8000
