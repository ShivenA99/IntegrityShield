/**
 * Get the base path for the application
 * Automatically detects GitHub Pages base path
 */
export const getBasePath = (): string => {
  // Check if we're on GitHub Pages by looking at the pathname
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/fairtestai_-llm-assessment-vulnerability-simulator-main')) {
    return '/fairtestai_-llm-assessment-vulnerability-simulator-main';
  }
  // Use Vite's base URL if available (for builds)
  if (import.meta.env.BASE_URL && import.meta.env.BASE_URL !== '/') {
    return import.meta.env.BASE_URL.replace(/\/$/, ''); // Remove trailing slash
  }
  return '';
};

/**
 * Get an asset URL with the correct base path
 */
export const getAssetUrl = (path: string): string => {
  const base = getBasePath();
  // Ensure path starts with /
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
};

