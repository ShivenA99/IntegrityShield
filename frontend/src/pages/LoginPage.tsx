import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@instructure/ui-buttons";

import PublicShell from "@layout/PublicShell";
import { useAuth } from "@contexts/AuthContext";
import { apiClient } from "@services/api";

const API_PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
  { id: "grok", label: "Grok" },
  { id: "anthropic", label: "Anthropic" },
];

const steps = [
  { id: 1, title: "Sign in" },
  { id: 2, title: "Configure providers" },
];

const LoginPage: React.FC = () => {
  const { login, register, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [currentStep, setCurrentStep] = useState(1);
  const [formState, setFormState] = useState({ name: "", email: "", password: "" });
  const [formErrors, setFormErrors] = useState<{ email?: string; password?: string; general?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiStatus, setApiStatus] = useState<Record<string, "pending" | "checking" | "ready" | "error">>({
    openai: "pending",
    gemini: "pending",
    grok: "pending",
    anthropic: "pending",
  });
  const [connectionHealthy, setConnectionHealthy] = useState(true);
  const [savingKeys, setSavingKeys] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard", { replace: true });
    }
  }, [isAuthenticated, navigate]);

  // Load existing API keys when reaching step 2
  useEffect(() => {
    if (currentStep === 2 && isAuthenticated) {
      loadApiKeys();
    }
  }, [currentStep, isAuthenticated]);

  const loadApiKeys = async () => {
    try {
      const response = await apiClient.getApiKeys();
      // Note: API keys are not returned for security, only metadata
      // We'll just mark them as configured if they exist
      const existingProviders = new Set(response.api_keys.map((k: any) => k.provider));
      setApiStatus((prev) => {
        const updated = { ...prev };
        existingProviders.forEach((provider) => {
          updated[provider] = "ready";
        });
        return updated;
      });
    } catch (error) {
      console.error("Failed to load API keys:", error);
    }
  };

  const handleSignIn = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormErrors({});
    setSubmitting(true);

    const errors: typeof formErrors = {};
    if (!formState.email.trim()) {
      errors.email = "Email is required.";
    }
    if (!formState.password.trim()) {
      errors.password = "Password is required.";
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      setSubmitting(false);
      return;
    }

    try {
      if (isRegisterMode) {
        await register({
          email: formState.email,
          password: formState.password,
          name: formState.name || undefined,
        });
      } else {
        await login({
          email: formState.email,
          password: formState.password,
        });
      }
      // Success - move to step 2
      setCurrentStep(2);
    } catch (error: any) {
      setFormErrors({
        general: error.message || "Authentication failed. Please try again.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleProviderCheck = async (providerId: string) => {
    const apiKey = apiKeys[providerId]?.trim();
    if (!apiKey) {
      setFormErrors({ general: "Please enter an API key first" });
      return;
    }

    setApiStatus((prev) => ({ ...prev, [providerId]: "checking" }));
    try {
      const result = await apiClient.validateApiKey(providerId, apiKey);
      if (result.valid) {
        setApiStatus((prev) => ({ ...prev, [providerId]: "ready" }));
      } else {
        setApiStatus((prev) => ({ ...prev, [providerId]: "error" }));
        setFormErrors({ general: result.message || "API key validation failed" });
      }
    } catch (error: any) {
      setApiStatus((prev) => ({ ...prev, [providerId]: "error" }));
      setFormErrors({ general: error.message || "Failed to validate API key" });
    }
  };

  const handleSaveApiKey = async (providerId: string) => {
    const apiKey = apiKeys[providerId]?.trim();
    if (!apiKey) {
      return;
    }

    try {
      await apiClient.saveApiKey(providerId, apiKey);
      setApiStatus((prev) => ({ ...prev, [providerId]: "ready" }));
    } catch (error: any) {
      setFormErrors({ general: error.message || "Failed to save API key" });
    }
  };

  const handleComplete = async () => {
    setSavingKeys(true);
    try {
      // Save all entered API keys
      const savePromises = Object.entries(apiKeys)
        .filter(([_, key]) => key.trim())
        .map(([provider, key]) => apiClient.saveApiKey(provider, key.trim()));

      await Promise.all(savePromises);
      navigate("/dashboard", { replace: true });
    } catch (error: any) {
      setFormErrors({ general: error.message || "Failed to save API keys" });
    } finally {
      setSavingKeys(false);
    }
  };

  const providerRows = useMemo(
    () =>
      API_PROVIDERS.map((provider) => {
        const status = apiStatus[provider.id];
        const configured = status === "ready";
        const checking = status === "checking";
        const hasError = status === "error";
        return {
          ...provider,
          configured,
          checking,
          hasError,
          statusLabel: configured
            ? "Ready"
            : checking
              ? "Checking…"
              : hasError
                ? "Error"
                : "Optional",
        };
      }),
    [apiStatus]
  );

  return (
    <PublicShell>
      <div className="wizard">
        <div className="wizard__steps">
          {steps.map((step) => (
            <div
              key={step.id}
              className={clsx(
                "wizard-step",
                currentStep === step.id ? "is-active" : "",
                currentStep > step.id ? "is-complete" : ""
              )}
            >
              <span>{step.id}</span>
              <p>{step.title}</p>
            </div>
          ))}
        </div>
        <span className={clsx("connection-banner", connectionHealthy ? "is-online" : "is-offline")}>
          {connectionHealthy ? "API reachable" : "API unreachable — check server"}
        </span>
        {currentStep === 1 ? (
          <section className="canvas-card wizard-card">
            <header className="wizard-card__header">
              <div>
                <p className="wizard-eyebrow">Step 1 of 2</p>
                <h2>{isRegisterMode ? "Create Account" : "Sign in"}</h2>
                <p>
                  {isRegisterMode
                    ? "Create your IntegrityShield account to get started."
                    : "Use your IntegrityShield credentials to sign in."}
                </p>
              </div>
              <Button as={Link} to="/" color="secondary" withBackground={false}>
                Back to Home
              </Button>
            </header>
            {formErrors.general && (
              <div className="form-error-banner" style={{ padding: "1rem", marginBottom: "1rem", backgroundColor: "#fee", color: "#c33", borderRadius: "4px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <AlertCircle size={16} />
                <span>{formErrors.general}</span>
              </div>
            )}
            <form className="form-grid" onSubmit={handleSignIn}>
              {isRegisterMode && (
                <label>
                  <span>Name</span>
                  <input
                    type="text"
                    value={formState.name}
                    onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                    placeholder="Optional"
                  />
                </label>
              )}
              <label>
                <span>Email</span>
                <input
                  type="email"
                  value={formState.email}
                  onChange={(event) => setFormState((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="you@example.com"
                  aria-invalid={Boolean(formErrors.email)}
                />
                {formErrors.email ? <small className="form-error">{formErrors.email}</small> : null}
              </label>
              <label>
                <span>Password</span>
                <input
                  type="password"
                  value={formState.password}
                  onChange={(event) => setFormState((prev) => ({ ...prev, password: event.target.value }))}
                  placeholder="••••••••"
                  aria-invalid={Boolean(formErrors.password)}
                />
                {formErrors.password ? <small className="form-error">{formErrors.password}</small> : null}
                {isRegisterMode && (
                  <small style={{ color: "#666", fontSize: "0.875rem" }}>
                    Must be at least 8 characters with uppercase, lowercase, and a number
                  </small>
                )}
              </label>
              <div className="wizard-actions">
                <Button type="submit" color="primary" interaction={submitting ? "disabled" : "enabled"}>
                  {submitting ? (
                    <>
                      <Loader2 size={16} className="spin" /> {isRegisterMode ? "Creating Account..." : "Signing in..."}
                    </>
                  ) : (
                    isRegisterMode ? "Create Account" : "Sign in"
                  )}
                </Button>
                <Button
                  type="button"
                  color="secondary"
                  withBackground={false}
                  onClick={() => {
                    setIsRegisterMode(!isRegisterMode);
                    setFormErrors({});
                  }}
                >
                  {isRegisterMode ? "Already have an account? Sign in" : "Don't have an account? Register"}
                </Button>
              </div>
            </form>
          </section>
        ) : null}

        {currentStep === 2 ? (
          <section className="canvas-card wizard-card" id="providers">
            <header className="wizard-card__header">
              <div>
                <p className="wizard-eyebrow">Step 2 of 2</p>
                <h2>Configure providers</h2>
                <p>Providers are optional. Add keys if you'd like IntegrityShield to run multi-provider evaluation comparisons.</p>
              </div>
            </header>

            {formErrors.general && (
              <div className="form-error-banner" style={{ padding: "1rem", marginBottom: "1rem", backgroundColor: "#fee", color: "#c33", borderRadius: "4px", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <AlertCircle size={16} />
                <span>{formErrors.general}</span>
              </div>
            )}

            <div className="provider-grid">
              {providerRows.map((provider) => (
                <div key={provider.id} className="provider-card">
                  <div className="provider-card__header">
                    <div>
                      <strong>{provider.label}</strong>
                      <span>Optional</span>
                    </div>
                    <span
                      className={clsx(
                        "status-pill",
                        provider.configured
                          ? "completed"
                          : provider.checking
                            ? "running"
                            : provider.hasError
                              ? "error"
                              : "pending"
                      )}
                    >
                      {provider.statusLabel}
                    </span>
                  </div>
                  <input
                    type="password"
                    placeholder={`Enter your ${provider.label} API key`}
                    value={apiKeys[provider.id] ?? ""}
                    onChange={(event) => {
                      setApiKeys((prev) => ({ ...prev, [provider.id]: event.target.value }));
                      if (apiStatus[provider.id] === "error") {
                        setApiStatus((prev) => ({ ...prev, [provider.id]: "pending" }));
                      }
                    }}
                  />
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <Button
                      type="button"
                      color="secondary"
                      withBackground={false}
                      onClick={() => handleProviderCheck(provider.id)}
                      interaction={provider.checking ? "disabled" : "enabled"}
                    >
                      {provider.configured ? (
                        <>
                          <CheckCircle2 size={16} /> Ready
                        </>
                      ) : provider.checking ? (
                        <>
                          <Loader2 size={16} className="spin" /> Checking…
                        </>
                      ) : (
                        "Validate"
                      )}
                    </Button>
                    {apiKeys[provider.id]?.trim() && !provider.configured && (
                      <Button
                        type="button"
                        color="primary"
                        withBackground={false}
                        onClick={() => handleSaveApiKey(provider.id)}
                      >
                        Save
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <footer className="wizard-footer">
              <div className="wizard-footer__note">You can revisit provider settings later in the tool.</div>
              <div className="wizard-footer__actions">
                <Button
                  type="button"
                  color="secondary"
                  onClick={() => navigate("/dashboard", { replace: true })}
                  interaction={savingKeys ? "disabled" : "enabled"}
                >
                  Skip provider setup
                </Button>
                <Button
                  type="button"
                  color="primary"
                  onClick={handleComplete}
                  interaction={savingKeys ? "disabled" : "enabled"}
                >
                  {savingKeys ? (
                    <>
                      <Loader2 className="spin" size={16} /> Saving...
                    </>
                  ) : (
                    "Continue to Dashboard"
                  )}
                </Button>
              </div>
            </footer>
          </section>
        ) : null}
      </div>
    </PublicShell>
  );
};

export default LoginPage;
