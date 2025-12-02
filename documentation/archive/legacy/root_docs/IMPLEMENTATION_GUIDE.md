# Complete Implementation Guide

## Test Scripts Created

1. **`test_fresh_run_api.py`** - Tests complete fresh run flow
2. **`test_rerun_api.py`** - Tests re-run with mapping preservation

## Critical Fixes Needed

### 1. PDF Rendering Fix (PRIORITY 1)

**File**: `frontend/src/components/pipeline/PdfCreationPanel.tsx`

**Problem**: PDFs aren't rendering in iframe because `relative_path` might be absolute path

**Fix**:
```typescript
const resolveRelativePath = (meta: EnhancedPDF) => {
  const rawPath = meta.relative_path || meta.path || meta.file_path || "";

  // If path is absolute, extract relative part
  if (rawPath.includes('/pipeline_runs/')) {
    const parts = rawPath.split('/pipeline_runs/');
    if (parts.length > 1) {
      // Remove run_id from path since URL already has it
      const afterRunId = parts[1].split('/').slice(1).join('/');
      return afterRunId;
    }
  }

  return rawPath;
};
```

### 2. Auto-Advance Prevention (PRIORITY 1)

**File**: `frontend/src/components/pipeline/PipelineContainer.tsx`

**Current Code** (lines 34-57):
```typescript
useEffect(() => {
  if (autoFollow) {
    setSelectedStage(activeStage as PipelineStageName);
  }
}, [activeStage, autoFollow]);
```

**Fix**:
```typescript
useEffect(() => {
  // Only auto-follow if stage is actively running
  const currentStageData = status?.stages.find(s => s.name === activeStage);
  const isRunning = currentStageData?.status === 'running';

  if (autoFollow && isRunning) {
    setSelectedStage(activeStage as PipelineStageName);
  }

  // Disable autoFollow when stage completes
  if (currentStageData?.status === 'completed') {
    setAutoFollow(false);
  }
}, [activeStage, autoFollow, status?.stages]);
```

### 3. Prevent Re-execution of Completed Stages (PRIORITY 2)

**File**: `frontend/src/components/pipeline/ContentDiscoveryPanel.tsx`

Add before line 20:
```typescript
const hasAdvancedToNextStage = useMemo(() => {
  const currentIdx = status?.stages.findIndex(s => s.name === 'content_discovery') ?? -1;
  const nextIdx = status?.stages.findIndex(s => s.name === 'smart_substitution') ?? -1;
  const nextStage = status?.stages[nextIdx];

  return nextIdx > currentIdx && nextStage && nextStage.status !== 'pending';
}, [status?.stages]);
```

Update button (line 66):
```typescript
<button
  type="button"
  className="pill-button"
  onClick={handleAdvance}
  disabled={isAdvancing || hasAdvancedToNextStage}
>
  {hasAdvancedToNextStage ? 'Already Advanced ✓' : (isAdvancing ? 'Advancing…' : 'Continue to Smart Substitution →')}
</button>
```

### 4. Move Action Buttons to Top Right (PRIORITY 2)

**All Panel Files**:
- ContentDiscoveryPanel.tsx
- SmartSubstitutionPanel.tsx
- PdfCreationPanel.tsx

**Pattern**:
```typescript
return (
  <div className="panel">
    {/* Header with action in top right */}
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      marginBottom: '1rem'
    }}>
      <h2>📑 Stage Name</h2>

      {stage?.status === 'completed' && !hasAdvanced && (
        <button
          className="pill-button"
          onClick={handleAdvance}
          disabled={isAdvancing}
          style={{
            backgroundColor: 'rgba(56,189,248,0.3)',
            padding: '8px 16px'
          }}
        >
          Continue to Next Stage →
        </button>
      )}
    </div>

    {/* Rest of panel content */}
  </div>
);
```

### 5. Fix Previous Runs Page (PRIORITY 2)

**File**: `frontend/src/pages/PreviousRuns.tsx`

**Changes**:
1. Remove "🗑️ Delete" button (hard delete)
2. Change "💤 Soft delete" to "🗑️ Delete"
3. Hide delete button if already deleted

Lines 197-213, replace with:
```typescript
{!r.deleted && (
  <button
    className="pill-button"
    onClick={() => onSoftDelete(r.run_id)}
    title="Mark run as deleted"
    style={{
      background: 'rgba(239,68,68,0.15)',
      color: '#fca5a5'
    }}
  >
    🗑️ Delete
  </button>
)}
```

### 6. Fix Re-run Backend Logic (PRIORITY 3)

**File**: `backend/app/api/pipeline_routes.py`

At line 527 (after copying substring_mappings), add logging:
```python
# After line 528
db.session.add(clone)

# Add this logging
logger.info(
    f"Cloned question {qnum} with {len(mappings_copy)} mappings",
    extra={"run_id": new_id, "source_run_id": source_run_id}
)
```

Add verification at the end (after line 550):
```python
db.session.commit()

# Verify mappings were copied
cloned_count = QuestionManipulation.query.filter_by(pipeline_run_id=new_id).count()
cloned_with_mappings = db.session.query(QuestionManipulation).filter(
    QuestionManipulation.pipeline_run_id == new_id,
    QuestionManipulation.substring_mappings != None,
    QuestionManipulation.substring_mappings != '[]'
).count()

logger.info(
    f"Re-run {new_id} created from {source_run_id}: "
    f"{cloned_count} questions, {cloned_with_mappings} with mappings"
)
```

## Testing Procedure

### Test 1: Fresh Run
```bash
cd backend
.venv/bin/python test_fresh_run_api.py
```

Expected output:
- Pipeline starts successfully
- Stages complete: smart_reading → content_discovery
- Questions are discovered
- Mappings are added
- PDF creation runs
- Enhanced PDFs are generated

### Test 2: Re-run
```bash
cd backend
.venv/bin/python test_rerun_api.py
```

Expected output:
- Re-run is created from source
- Questions are copied with mappings
- Current stage is 'smart_substitution'
- Mappings match source run
- PDF creation generates same number of PDFs

### Test 3: UI Flow
1. Start servers (already running)
2. Upload Quiz6.pdf
3. Wait for content_discovery to complete
4. Verify button appears at **top right**: "Continue to Smart Substitution →"
5. Click button - should NOT auto-advance until clicked
6. Add mappings on smart_substitution page
7. Click "Create Enhanced PDF" at **top right**
8. Verify PDFs render in iframe
9. Go to Previous Runs page
10. Click "Re-run" - verify new run has mappings copied

## Files That Need Changes

### Frontend (7 files)
1. ✅ `frontend/src/components/pipeline/PipelineContainer.tsx` - Auto-follow fix
2. ✅ `frontend/src/components/pipeline/ContentDiscoveryPanel.tsx` - Button position + prevent re-execution
3. ✅ `frontend/src/components/pipeline/SmartSubstitutionPanel.tsx` - Button position
4. ✅ `frontend/src/components/pipeline/PdfCreationPanel.tsx` - PDF rendering + button position
5. ✅ `frontend/src/pages/PreviousRuns.tsx` - Button labels
6. Optional: `frontend/src/components/pipeline/EffectivenessTestPanel.tsx` - Button position
7. Optional: `frontend/src/components/pipeline/ResultsPanel.tsx` - Disable by default

### Backend (1 file)
1. ✅ `backend/app/api/pipeline_routes.py` - Enhanced re-run logic with verification

## Implementation Order

1. **PDF Rendering** (5 min) - Critical for seeing results
2. **Auto-Advance Prevention** (5 min) - Critical for UX
3. **Button Positioning** (15 min) - Improves discoverability
4. **Prevent Re-execution** (10 min) - Prevents errors
5. **Previous Runs UI** (5 min) - Cleanup
6. **Backend Re-run Logging** (5 min) - Better debugging
7. **Run Tests** (10 min) - Validation

**Total Estimated Time**: ~55 minutes

## Quick Start

To implement all fixes quickly, run:
```bash
# Implement all frontend fixes
cd frontend/src
# Apply the pattern from sections 1-5 above to each file

# Implement backend fix
cd ../../backend/app/api
# Add the logging from section 6

# Test
cd ../../
.venv/bin/python test_fresh_run_api.py
.venv/bin/python test_rerun_api.py
```