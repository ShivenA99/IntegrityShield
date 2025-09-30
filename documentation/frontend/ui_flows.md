# UI Flows & Screens

This section documents the major screens in the SPA, their responsibilities, and primary interactions with the backend.

## 1. Upload & Start (`/dashboard` when no active run)
- **Purpose:** Let users upload a new PDF or resume a recent run.
- **Components:** `UploadCard`, `RecentRunsList`, `FileDropZone`.
- **Actions:**
  - `POST /api/pipeline/start` with selected file.
  - Persist `run_id` to local storage via `saveRecentRun`.
  - Automatically navigates to the active run dashboard once `smart_reading` begins.

## 2. Active Run Dashboard (`/dashboard` with run)
- **Purpose:** Monitor pipeline progress, edit question mappings, resume paused runs.
- **Layout:**
  - **Header:** pipeline status, resume/reset buttons, developer toggle.
  - **Pipeline Timeline:** Visual stage tracker (uses `status.stages`).
  - **Question Workspace:**
    - `SmartSubstitutionPanel`: lists questions, substring mappings, geometry previews.
    - `OverlayPreview`: shows bounding boxes on page thumbnails (if available).
  - **Actions Drawer:** Resume pipeline (`/resume/pdf_creation`), run validations/tests.
- **Key Interactions:**
  - Fetch questions via `GET /api/questions/<run>`.
  - Save mappings with `PUT /api/questions/<run>/<question_id>/manipulation` or bulk save.
  - Trigger validations/tests using dedicated buttons (calls GPT-5 validation, AI testing).

## 3. Previous Runs (`/previous-runs`)
- **Purpose:** Inventory of historic runs with filtering, rerun, and delete controls.
- **Components:** `RunsTable`, filter controls, search box.
- **Actions:**
  - `GET /api/pipeline/runs` with filters.
  - `🔁 Re-run` button → `POST /api/pipeline/rerun` (then polls status).
  - `👁️ View` navigates to dashboard and sets active run.
  - `📄 JSON` downloads structured payload.
  - Delete operations call `POST /soft_delete` or `DELETE` depending on user choice.

## 4. Developer Console (`/developer`)
- **Purpose:** Troubleshooting hub for engineers.
- **Features:**
  - Live log stream viewer (subscribes to SSE).
  - Performance metrics table (stage durations, memory usage).
  - Buttons to replay overlays, inspect structured JSON, or clear caches (if enabled).
  - Search/filter logs by stage or severity.

## 5. Results & Artifacts
- **Accessed via:** Dashboard side panel after `pdf_creation`/`results_generation` complete.
- **Displays:**
  - Download links for `after_stream_rewrite.pdf`, `final.pdf`, mask overlays.
  - Effectiveness scores and AI testing summaries.
  - Stage validation badges (success/failure).

## Interaction Notes

- **Pause/Resume:** Dashboard surfaces a "Resume PDF Creation" button when the pipeline is paused after `content_discovery`.
- **Developer Mode:** Toggle reveals extra tabs (raw logs, structured JSON viewer, overlay debug images).
- **Error Surfacing:** API failures generate toast notifications and appear in the developer console with structured details.

Keep this document updated when new screens or flows are introduced.
