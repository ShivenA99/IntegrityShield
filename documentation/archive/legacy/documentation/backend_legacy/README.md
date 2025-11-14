# Backend Documentation Index

The backend is a Flask application that orchestrates multi-stage PDF manipulation pipelines, interfaces with AI services, and serves REST endpoints to the React SPA. Use the files below for deep dives:

- [architecture.md](architecture.md) — service layout, key modules, threading model, third-party integrations.
- [pipeline.md](pipeline.md) — end-to-end stage behavior (`smart_reading` through `results_generation`) with inputs, outputs, and pause/resume rules.
- [api_reference.md](api_reference.md) — REST endpoints, request/response shapes, auth, and common failure modes.
- [logging.md](logging.md) — logging infrastructure, live log streaming, standard log keys, and troubleshooting tips.
- [testing.md](testing.md) — unit/integration test scaffold, manual run checklists, and instrumentation for QA.
- [pipeline_methods.md](pipeline_methods.md) — details of PDF generation methods (stream rewrite vs overlay) and their artifacts.

Update this index whenever a new backend doc is added.
