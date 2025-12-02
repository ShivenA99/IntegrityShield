# GitHub Pages Build

This directory contains the built React application for GitHub Pages.

## Building for GitHub Pages

To rebuild the site after making changes:

```bash
cd frontend
npm run build:gh-pages
```

This will:
1. Build the React app with the correct base path for GitHub Pages
2. Output the files to the `docs/` directory
3. Create a `.nojekyll` file to disable Jekyll processing

## GitHub Pages Configuration

1. Go to your repository settings on GitHub
2. Navigate to "Pages" in the left sidebar
3. Under "Source", select "Deploy from a branch"
4. Select the branch (e.g., `eacl-demo` or `main`)
5. Select `/docs` as the folder
6. Click "Save"

Your site will be available at:
`https://ShivenA99.github.io/integrityshield_-llm-assessment-vulnerability-simulator-main/`

## Notes

- The `404.html` file is a copy of `index.html` to handle client-side routing
- The `.nojekyll` file disables Jekyll processing so GitHub Pages serves the static files directly
- The base path is automatically configured for the repository name

