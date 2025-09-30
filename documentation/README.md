# FairTestAI LLM Vulnerability Simulator — Documentation Hub

Welcome to the consolidated documentation set for the FairTestAI "LLM Assessment Vulnerability Simulator". The goal of this folder is to provide a single, well-organized location for all engineering knowledge about the platform so that future Codex agents (or human contributors) can ramp up rapidly and keep the docs current after each major change.

## Structure

```
documentation/
├─ README.md                # This file – directory map & contribution guidance
├─ backend/                 # Services, pipelines, APIs, logging, testing
├─ frontend/                # UI architecture, core flows, component registry
├─ data/                    # Database schema, structured JSON, artifacts
├─ prompts/                 # AI prompt catalog and usage notes
└─ operations/              # Dev workflows, environment setup, maintenance
```

Each subtree contains standalone markdown files that can be updated independently. When you touch a feature, update the relevant doc file and add a brief note under `operations/change-log.md` so history stays auditable.

## Keeping Documentation Fresh

1. **During development** – note major architectural or behavioral changes in the relevant doc file immediately.
2. **Before merging** – skim the table of contents below and make sure modified domains are covered.
3. **After releases** – append a short summary to `operations/change-log.md` (date, change set, point of contact).

## Table of Contents

- [Backend](backend/README.md)
  - [Architecture Overview](backend/architecture.md)
  - [Pipeline & Stage Behaviors](backend/pipeline.md)
  - [API Reference](backend/api_reference.md)
  - [Logging & Telemetry](backend/logging.md)
  - [Testing & Validation](backend/testing.md)
- [Frontend](frontend/README.md)
  - [SPA Architecture](frontend/architecture.md)
  - [UI Screens & Flows](frontend/ui_flows.md)
  - [Component Catalog](frontend/components.md)
- [Data & Storage](data/README.md)
  - [Database Schema](data/database.md)
  - [Structured JSON Contracts](data/structured_payloads.md)
  - [File Artifacts & Conventions](data/artifacts.md)
- [Prompts & AI Integrations](prompts/README.md)
- [Operations](operations/README.md)
  - [Environment & Tooling](operations/environment.md)
  - [Development Workflow](operations/development.md)
  - [Change Log](operations/change-log.md)

## Contributing to Docs

- Prefer short, scannable sections with direct links to source files.
- Add diagrams or ASCII flows when they clarify the pipeline.
- When documenting API or schema changes, include the version or commit hash.

Need to document something not listed? Create a new file, add it to the appropriate README, and keep the structure consistent.
