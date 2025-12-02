# Documentation Index

Welcome to the living guide for the AntiCheatAI vulnerability simulator. This index links to the current, non-legacy documentation that reflects the `AntiCheat-v0.0` branch status. Every feature change should be paired with an update in the appropriate section to keep this knowledge base trustworthy.

## How To Use These Docs

- **New contributors** – start with [setup.md](setup.md) to get the backend/frontend running.
- **Feature work** – reference [backend.md](backend.md), [frontend.md](frontend.md), and [pipeline.md](pipeline.md) for architecture and stage behaviour.
- **Data-focused tasks** – consult [data.md](data.md) for schema/storage layouts and [models-and-attacks.md](models-and-attacks.md) for configurable AI levers.
- **Operational tasks** – see [operations.md](operations.md) for day-to-day workflows and release hygiene.
- **Prompt tuning** – use [prompts.md](prompts.md) for the current AI prompt catalogue.

## Table of Contents

- [setup.md](setup.md) — prerequisites, environment variables, backend/frontend bootstrapping
- [overview.md](overview.md) — platform goals, user journeys, and component map
- [backend.md](backend.md) — Flask architecture, pipeline services, API surface, logging, migrations
- [frontend.md](frontend.md) — SPA layout, stage UX, shared components, styling system
- [pipeline.md](pipeline.md) — stage-by-stage behaviour, classroom dataset lifecycle, failure modes
- [data.md](data.md) — database schema (including classroom tables), structured JSON, filesystem artifacts
- [models-and-attacks.md](models-and-attacks.md) — default model roster, enhancement methods, configuration knobs
- [prompts.md](prompts.md) — prompt templates, locations in code, maintenance notes
- [operations.md](operations.md) — development workflow, testing strategy, troubleshooting, logging tips

## Legacy References

Older documents that no longer describe the active system are stored under [`documentation/archive/`](archive/) for historical context. Do not rely on them for implementation decisions.

## Keeping Documentation Fresh

1. Update the relevant markdown file while the change is still in your working tree.
2. Mention the doc update in your PR description.
3. If a change invalidates a section, rewrite it instead of appending a warning—clarity beats nostalgia.
