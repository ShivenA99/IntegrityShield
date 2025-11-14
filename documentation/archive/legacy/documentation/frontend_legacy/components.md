# Component Catalog

This file highlights high-impact React components and where to find them. For prop signatures, open the corresponding `.tsx` file.

## Core Layout

| Component | Path | Notes |
| --- | --- | --- |
| `Header` | `components/layout/Header.tsx` | Displays active run info, reset/rerun controls, developer toggle. |
| `Sidebar` | `components/layout/Sidebar.tsx` | Navigation links (Dashboard, Previous Runs, Developer). |
| `MainPanel` | `components/layout/MainPanel.tsx` | Main content wrapper; handles responsive padding and scroll. |

## Dashboard Widgets

| Component | Path | Purpose |
| --- | --- | --- |
| `PipelineTimeline` | `components/pipeline/PipelineTimeline.tsx` | Stage progression, duration badges, pause indicators. |
| `StageCard` | `components/pipeline/StageCard.tsx` | Displays per-stage details, status pills, action buttons. |
| `SmartSubstitutionPanel` | `components/pipeline/SmartSubstitutionPanel.tsx` | Lists questions, substring mappings, geometry previews; allows inline edits. |
| `OverlayPreview` | `components/pipeline/OverlayPreview.tsx` | Renders page thumbnail with overlay boxes for selected mapping. |
| `EffectivenessPanel` | `components/pipeline/EffectivenessPanel.tsx` | Shows AI testing results and allows retriggering tests. |

## Previous Runs

| Component | Path | Purpose |
| --- | --- | --- |
| `RunsTable` | `pages/PreviousRuns.tsx` | Data table of runs with filters and actions (view/download/rerun/delete). |
| `RunFilters` | `pages/PreviousRuns.tsx` (inline) | Search bar, status checkboxes, sort dropdowns. |

## Developer Tools

| Component | Path | Purpose |
| --- | --- | --- |
| `DeveloperConsole` | `pages/DeveloperConsole.tsx` | Aggregates logs, metrics, structured JSON viewer. |
| `LogStream` | `components/developer/LogStream.tsx` | Real-time log feed with filtering. |
| `MetricsTable` | `components/developer/MetricsTable.tsx` | Displays `performance_metrics` entries. |

## Forms & Utilities

| Component | Path | Purpose |
| --- | --- | --- |
| `FileDropZone` | `components/forms/FileDropZone.tsx` | Drag & drop upload area for PDFs. |
| `Toggle` | `components/common/Toggle.tsx` | Generic toggle switch used across settings. |
| `Toast` | `components/feedback/Toast.tsx` | Notification pop-ups managed by `useToast`. |
| `DataTable` | `components/common/DataTable.tsx` | Reusable table with sorting/pagination (used by runs/questions lists). |

## Hooks & Context Helpers

These aren’t visual components but drive component behavior:

| Hook | Path | Purpose |
| --- | --- | --- |
| `usePipeline` | `hooks/usePipeline.ts` | Access current run, refresh status, rerun/reset actions. |
| `useDeveloperTools` | `hooks/useDeveloperTools.ts` | Log subscription, metric polling. |
| `useOverlayPreview` | `hooks/useOverlayPreview.ts` | Manage overlay snapshots for selected mapping. |
| `usePolling` | `hooks/usePolling.ts` | Generic polling helper (used for status refresh). |

When adding new components, document them here with a short description so future agents know where to look.
