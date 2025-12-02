# GitHub Pages Setup Guide

Your React landing pages are now configured to work with GitHub Pages!

## What Was Configured

1. **Build Configuration**: Updated `frontend/vite.config.ts` to build to the `/docs` folder with the correct base path
2. **Router Configuration**: Updated `frontend/src/main.tsx` to automatically detect and use the correct base path for GitHub Pages
3. **Jekyll Disabled**: Created `docs/.nojekyll` to prevent Jekyll from processing the static files
4. **404 Handling**: Created `docs/404.html` (copy of index.html) to handle client-side routing
5. **GitHub Pages Config**: Updated `_config.yml` to disable Jekyll processing

## How to Enable GitHub Pages

1. Go to your GitHub repository: https://github.com/ShivenA99/integrityshield_-llm-assessment-vulnerability-simulator-main
2. Click on **Settings** (top menu)
3. Scroll down to **Pages** in the left sidebar
4. Under **Source**, select:
   - **Branch**: Choose your branch (e.g., `eacl-demo` or `main`)
   - **Folder**: Select `/docs`
5. Click **Save**

## Your Site URL

Once enabled, your site will be available at:
```
https://ShivenA99.github.io/integrityshield_-llm-assessment-vulnerability-simulator-main/
```

## Rebuilding After Changes

Whenever you make changes to the frontend and want to update GitHub Pages:

```bash
cd frontend
npm run build:gh-pages
git add docs/
git commit -m "Update GitHub Pages build"
git push
```

GitHub Pages will automatically rebuild within a few minutes.

## Notes

- The landing page (`/`) will show your `LandingPage` component
- All routes will work correctly thanks to the `404.html` file
- The base path is automatically detected, so it works both locally and on GitHub Pages

