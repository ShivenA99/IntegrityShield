# Frontend Guide

The frontend is a Vite-powered React application that provides an interactive UI for generating and downloading manipulated fonts/PDFs.

## Directory Structure

| Path | Description |
| --- | --- |
| `frontend/index.html` | Vite entry HTML file. |
| `frontend/package.json` | npm metadata and scripts (`dev`, `build`, `preview`). |
| `frontend/vite.config.js` | Vite configuration (proxy adjustments if needed). |
| `frontend/src/main.jsx` | Bootstraps React root. |
| `frontend/src/App.jsx` | Top-level component orchestrating data fetching and state. |
| `frontend/src/App.css`, `frontend/src/index.css` | Global styling. |
| `frontend/src/components/` | Reusable UI building blocks. |
| `frontend/node_modules/` | Installed dependencies (ignored by git). |

### Components

| Component | Purpose |
| --- | --- |
| `ModeSelector` | Renders available manipulation modes returned by `/api/modes`; updates the selected mode in `App`. |
| `ManipulationForm` | Collects `visualWord` and `hiddenWord`, performs length validation, and triggers `handleManipulate`. |
| `ResultDisplay` | Shows loading, success, or empty states; exposes download links for generated files and instructions. |

All components reside under `frontend/src/components/`. Styles for each component live beside their `.jsx` files (e.g., `ResultDisplay.css`).

## API Integration

- Base URL: `http://localhost:5001/api` (defined at the top of `App.jsx`).
- Endpoints used: `/modes`, `/health`, `/manipulate`.
- On submission, the app POSTs `{ mode, visual_word, hidden_word }` to `/manipulate` and expects a payload containing `pdf_file`, optional `font_file`, and `message`.
- `ResultDisplay` composes download URLs using the backend’s `/api/download/<filename>` route.

## Running the Frontend

```bash
cd frontend
npm install
npm run dev  # defaults to http://localhost:5173
```

During development, ensure the backend runs on `http://localhost:5001` so the proxy can resolve API calls. For production builds, run `npm run build` and deploy the `dist/` folder behind a static server with the desired backend host configured.

## Troubleshooting

- **CORS Errors**: Confirm the backend is up and CORS is enabled (handled by `flask_cors.CORS` in `app.py`).
- **Connection Refused**: Backend might not be reachable; check port 5001 or adjust `API_URL` in `App.jsx`.
- **Download 404**: The output files are removed or the job failed; check backend logs under `backend/outputs/logs/`.

## Update Checklist

- Document new components as they are introduced.
- Update screenshots or demos in separate documentation if UI changes significantly.
- Reflect any API contract changes in this guide and adjust `App.jsx` accordingly.
