# Frontend Architecture & UX

The frontend is a React + TypeScript SPA (Vite) that guides users through pipeline execution, mapping validation, and classroom analytics. This document covers the application shell, state management, key screens, and styling conventions.

## Application Shell

| File | Responsibility |
| --- | --- |
| `frontend/src/main.tsx` | Bootstraps React, wraps `<App />` with context providers. |
| `frontend/src/App.tsx` | Registers routes (dashboard, previous runs, developer tools) and global layout. |
| `frontend/src/components/layout/` | Header, sidebar, footer, developer toggle. |
| `frontend/src/contexts/` | Pipeline status provider, classroom manager context, toast notifications, developer console. |
| `frontend/src/services/` | REST clients (`pipelineApi.ts`, `questionsApi.ts`), WebSocket/SSE connectors, TypeScript DTOs. |
| `frontend/src/styles/global.css` | Design tokens, gradient backgrounds, button styles, stage accent classes. |

Classroom workflows now live under `frontend/src/pages/Classrooms.tsx` and `frontend/src/pages/ClassroomEvaluation.tsx`, reached via the action buttons surfaced in Stage 4.
### State Management

- `PipelineContext` tracks the active run (`status`, `stages`, `enhanced_pdfs`, `classrooms`) and handles polling/resume logic.
- Stage actions derive availability from `PipelineContext` (download counts, classroom completion) and update preferred stage on completion.
- `ClassroomManagerContext` (embedded in Stage 5) manages datasets, filters, and evaluation results.
- `DeveloperToolsContext` subscribes to live logs and keeps panel preferences.
- Local component state drives UI controls (e.g., disable buttons after actions complete, collapse panels, hover tooltips).

## Stage Panels

| Stage | Component | Highlights |
| --- | --- | --- |
| Smart Reading | `SmartReadingPanel.tsx` | Upload UI, run creation, start button auto-disables once stage completes. |
| Content Discovery | `ContentDiscoveryPanel.tsx` | Shows question fusion progress, exposes "Continue to Smart Substitution". |
| Smart Substitution | `SmartSubstitutionPanel.tsx` | Mapping editor, validation/test triggers, stage advancement guard. |
| Download PDFs | `PdfCreationPanel.tsx` | Compact variant palette, overlay summaries, "Create PDFs" auto-disables after queue, surfaces Classroom/Evaluation action buttons once downloads exist. |
| Results & QA | `ProgressTracker.tsx`, `ContentDiscoveryPanel` summary | Stage chips show progress, tooltips provide status detail. |
| Classroom (action) | `pages/Classrooms.tsx` | Run/PDF picker, searchable & sortable dataset table, generation form with advanced config, import placeholder, success/error toasts. |
| Classroom Evaluation (action) | `pages/ClassroomEvaluation.tsx` | Dataset-specific analytics (cheating mix, scores, student table), re-evaluate button disabled while in flight, breadcrumbs back to classroom list. |

The first four panels map directly to orchestrator stages; classroom panels operate on `answer_sheet_runs` and `classroom_evaluations` records returned by `GET /pipeline/<run>/status`.

## Navigation & Layout

- **Sidebar** now presents a compact shield logo, consistent nav button sizing, and a redesigned run card (status pill, document, download/classroom chips, refresh/reset actions).
- **Pipeline run bar** (top of the dashboard) surfaces run metadata chips (document, stage, variant count, downloads, classrooms, evaluation coverage) and action icons (refresh, reset, developer toggle).
- **Stage actions row** sits beneath the tracker, exposing `Classroom` and `Evaluation` buttons with availability guards (disabled until downloads/classrooms exist).
- **Footer** displays logs/status hints.
- **Developer Console** (toggle in the run bar and sidebar card) slides in from the right, consuming live log streams and metrics.

## Styling Guidelines

- Utility classes in `global.css` define consistent typography, spacing, and gradient backgrounds. New tokens (`.pipeline-chip`, `.pipeline-stage-actions__button`, `.app-sidebar__run-chip`) keep run metadata and action buttons visually coherent.
- Buttons follow a "pill" aesthetic with disabled states and loading animations; selective actions (Classroom/Evaluation) expose secondary labels for counts.
- Tooltips (`title` attributes) are attached to icons, chips, and action buttons; keep copy concise (<80 chars) and note that disabled buttons still surface tooltips for guidance.

## API Consumption

- `pipelineApi.ts` centralises calls to backend endpoints; responses are typed via `services/types/pipeline.ts`.
- Classroom-related DTOs include `ClassroomDataset`, `ClassroomEvaluation`, and aggregated metrics; these are kept in sync with backend serializers.
- Polling uses exponential backoff and handles transient 404s immediately after creating a rerun or dataset.

## Adding or Modifying Screens

1. Update the relevant context or service with new data requirements.
2. Extend TypeScript interfaces to mirror backend payloads (keep optional fields typed correctly).
3. Modify or create components under `components/pipeline/` or `components/shared/`.
4. Wire the component into `PipelineContainer.tsx` with stage gating logic.
5. Add styles to `global.css`, preferring CSS variables and existing spacing scales.
6. Update documentation (`pipeline.md`, `frontend.md`) if UX flows change.

## Developer Experience

- **Hot Module Reloading** – Vite reloads components instantly; ensure modules export stable component identities.
- **ESLint + TypeScript** – `npm run lint` catches unused deps, type mismatches, and accessibility hints.
- **Storybook** – *Not currently configured*; consider adding if we build more complex component libraries.
- **Testing** – Frontend tests are not yet standardised. If you add them, document the workflow here.

Keep this file updated when route structure changes, new stages are introduced, or styling guidelines evolve.
