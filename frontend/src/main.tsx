import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { InstUISettingsProvider } from "@instructure/emotion";
import { theme as canvasTheme } from "@instructure/canvas-theme";

import App from "./App";
import "./styles/custom-overrides.css";

const ASU_ORANGE = "#FF7F32";
const ASU_ORANGE_HOVER = "#e0671c";
const ASU_ORANGE_ACTIVE = "#cc641f";

const integrityShieldTheme = {
  ...canvasTheme,
  colors: {
    ...canvasTheme.colors,

    // Brand colors (ASU Orange)
    brand: ASU_ORANGE,
    brandPrimary: ASU_ORANGE,
    primary: ASU_ORANGE,
    link: ASU_ORANGE,

    // Status colors
    textSuccess: "#0f9d58",
    textDanger: "#dc2626",
    textWarning: "#d97706",
    textInfo: "#0284c7",

    backgroundSuccess: "rgba(15, 157, 88, 0.15)",
    backgroundDanger: "rgba(220, 38, 38, 0.15)",
    backgroundWarning: "rgba(217, 119, 6, 0.15)",
    backgroundInfo: "rgba(2, 132, 199, 0.15)",

    // Backgrounds
    backgroundLightest: "#ffffff",
    backgroundLight: "#f9fafb",
    backgroundMedium: "#f5f6f7",
    backgroundDark: "#1f2933",
    backgroundBrand: ASU_ORANGE,
    backgroundBrandSecondary: "rgba(255, 127, 50, 0.12)",

    // Text colors
    textDarkest: "#1f2933",
    textDark: "#4b5563",
    textLight: "#6b7280",
    textLightest: "#9ca3af",
    textBrand: ASU_ORANGE,

    // Borders
    borderMedium: "#d8dde6",
    borderLight: "#e5e7eb",
    borderDark: "#9ca3af",
    borderBrand: ASU_ORANGE,
  },

  // Component-specific overrides
  components: {
    Button: {
      primaryBackground: ASU_ORANGE,
      primaryHoverBackground: ASU_ORANGE_HOVER,
      primaryActiveBackground: ASU_ORANGE_ACTIVE,
      primaryColor: "#ffffff",
      primaryBorderColor: ASU_ORANGE,

      secondaryBackground: "#ffffff",
      secondaryHoverBackground: "rgba(255, 127, 50, 0.08)",
      secondaryColor: ASU_ORANGE,
      secondaryBorderColor: ASU_ORANGE,
    },
    Link: {
      color: ASU_ORANGE,
      hoverColor: ASU_ORANGE_HOVER,
      activeColor: ASU_ORANGE_ACTIVE,
    },
    ProgressBar: {
      color: ASU_ORANGE,
    },
  },

  // Canvas legacy theme variables (for backward compatibility)
  "ic-brand-primary": ASU_ORANGE,
  "ic-brand-button--primary-bgd": ASU_ORANGE,
  "ic-brand-button--primary-text": "#ffffff",
  "ic-brand-button--secondary-bgd": "#ffffff",
  "ic-brand-button--secondary-text": ASU_ORANGE,
  "ic-link-color": ASU_ORANGE,
  "ic-link-decoration": "none",
};

// Get base path for GitHub Pages
const getBasePath = () => {
  // Check if we're on GitHub Pages by looking at the pathname
  if (window.location.pathname.startsWith('/fairtestai_-llm-assessment-vulnerability-simulator-main')) {
    return '/fairtestai_-llm-assessment-vulnerability-simulator-main';
  }
  return '';
};

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <InstUISettingsProvider theme={integrityShieldTheme}>
      <BrowserRouter basename={getBasePath()}>
        <App />
      </BrowserRouter>
    </InstUISettingsProvider>
  </React.StrictMode>
);
