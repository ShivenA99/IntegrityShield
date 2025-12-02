# Frontend Architecture

The UI is a React + TypeScript SPA bundled with Vite. It orchestrates pipeline uploads, mapping edits, and developer tooling.

## Application Shell

- **Entry Point:** `frontend/src/main.tsx` attaches `<App />` to the DOM.
- **Routing:** `App.tsx` configures React Router routes (`/dashboard`, `/previous-runs`, `/developer` etc.).
- **State Management:** Context hooks (`usePipeline`, `useDeveloperTools`, `useWorkspace`) provide run status, logging streams, and local storage helpers.
- **Styling:** Tailwind-inspired utility classes live under `frontend/src/styles/`, supplemented by CSS modules within components.

## Directory Map

| Folder | Contents |
| --- | --- |
| `components/` | UI primitives (panels, tables, buttons) and feature widgets (Pipeline timeline, Smart Substitution panel, Developer console). |
| `pages/` | Route-level components (`Dashboard`, `PreviousRuns`, `DeveloperConsole`, `UploadPage`). |
| `contexts/` | React context providers for pipeline status, developer logs, notification toasts. |
| `hooks/` | Custom hooks (`usePipeline`, `useDeveloperTools`, `useToast`, `usePolling`). |
| `services/` | API clients (`pipelineApi.ts`, `questionsApi.ts`), WebSocket/SSE handlers, type definitions (`types/`). |
| `constants/` | Shared enums, stage descriptions, default settings. |
| `assets/` | Icons, images. |

## Data Flow

1. **API Services:** `pipelineApi.ts` / `questionsApi.ts` wrap `axios` with interceptors for timing logs. They return typed responses consumed by hooks.
2. **Contexts:** `PipelineProvider` fetches status, handles rerun/reset logic, and persists recent run IDs in local storage.
3. **Pages:** Subscribe to contexts and render domain components. Example: `Dashboard` shows current run status, stage cards, question editors.
4. **Components:** `SmartSubstitutionPanel`, `PipelineTimeline`, `StageLogs`, `OverlayPreview` etc. encapsulate UI logic.
5. **Developer Tools:** `useDeveloperTools` subscribes to live log streams, surfaces metrics/alerts in the sidebar.

## Networking

- **REST Calls:** via `axios` (`client` configured in services). Requests include base URL `/api/...` (reverse-proxied to Flask).
- **Live Logs:** SSE/WebSocket client (see `services/developerLogs.ts`) streams events into `DeveloperToolsContext`.
- **Polling:** `usePipeline` polls `GET /pipeline/<run>/status` with exponential backoff (recently enhanced to retry 404 after rerun).

## Error Handling

- Global error boundary in `App.tsx` displays fallback screens.
- API errors bubble into contexts; toasts and developer console highlight issues (AI 5xx, validation failures).

## Build & Tooling

- Run `npm install` (or `pnpm` if configured) inside `/frontend`.
- Development server: `npm run dev` (uses Vite).
- Linting: `npm run lint` (ESLint + TypeScript).

Keep this document updated when the routing structure, state management approach, or build configuration changes.
