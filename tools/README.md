# API Helper Scripts

### `hit_api.py`

Minimal CLI wrapper around `requests` so you can hit the running backend from your shell.

Usage examples (run these from the repo root, outside the sandbox):

```bash
python tools/hit_api.py /api/health
python tools/hit_api.py /api/pipeline/123/status --method GET
python tools/hit_api.py /api/pipeline/rerun --method POST --json '{"run_id": "123"}'
```

Flags:
- `--host` / `--port` if the backend isn’t on `127.0.0.1:5000`
- `--headers` to pass a JSON object of extra headers

Feel free to extend this with additional helpers (auth flows, canned payloads, etc.).
