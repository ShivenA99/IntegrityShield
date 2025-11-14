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

### State Management

- `PipelineContext` tracks the active run (`status`, `stages`, `enhanced_pdfs`, `classrooms`) and handles polling/resume logic.
- `ClassroomManagerContext` (embedded in Stage 5) manages datasets, filters, and evaluation results.
- `DeveloperToolsContext` subscribes to live logs and keeps panel preferences.
- Local component state drives UI controls (e.g., disable buttons after actions complete, collapse panels, hover tooltips).

## Stage Panels

| Stage | Component | Highlights |
| --- | --- | --- |
| Smart Reading | `SmartReadingPanel.tsx` | Upload UI, run creation, start button auto-disables once stage completes. |
| Content Discovery | `ContentDiscoveryPanel.tsx` | Shows question fusion progress, exposes "Continue to Smart Substitution". |
| Smart Substitution | `SmartSubstitutionPanel.tsx` | Mapping editor, validation/test triggers, stage advancement guard. |
| PDF Creation | `PdfCreationPanel.tsx` | Variant palette (compacted card layout), auto-focus on Stage 4 completion, create button locks once invoked. |
| Results & QA | `ProgressTracker.tsx`, `ContentDiscoveryPanel` summary | Stage chips show progress, tooltips provide status detail. |
| Classroom Datasets | `ClassroomManagerPanel.tsx` | Distinct accent colour, searchable/filterable dataset table, create/import modal, success/error flashes, action dropdowns. |
| Classroom Evaluation | `ClassroomEvaluationPanel.tsx` | Tied to selected dataset, surfaces summary metrics, charts (score buckets, cheating breakdown), evaluate button disabled when in-flight or data missing. |

The first four panels map directly to orchestrator stages; classroom panels operate on `answer_sheet_runs` and `classroom_evaluations` records returned by `GET /pipeline/<run>/status`.

## Navigation & Layout

- **Sidebar** houses stage chips, previous runs, and developer toggle.
- **Header** surfaces active run metadata and global actions (resume pipeline, rerun).
- **Footer** displays logs/status hints.
- **Developer Console** (toggle in header) slides in from the right, consuming live log streams and metrics.

## Styling Guidelines

- Utility classes in `global.css` define consistent typography, spacing, and gradient backgrounds. Stage-specific modifiers (`.stage-card`, `.classroom-stage-strip`) keep the new classroom row visually distinct.
- Buttons follow a "pill" aesthetic with disabled states and loading animations.
- Tooltips (`data-tooltip`) provide hover hints for action icons; keep copy concise (<80 chars).

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
