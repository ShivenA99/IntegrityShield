import React, { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { CheckCircle2, Loader2 } from "lucide-react";
import { Button } from "@instructure/ui-buttons";

import PublicShell from "@layout/PublicShell";
import { useAuth } from "@contexts/AuthContext";

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
  const { login } = useAuth();
  const navigate = useNavigate();

  const [currentStep, setCurrentStep] = useState(1);
  const [formState, setFormState] = useState({ name: "", email: "", password: "" });
  const [formErrors, setFormErrors] = useState<{ email?: string; password?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiStatus, setApiStatus] = useState<Record<string, "pending" | "checking" | "ready">>({
    openai: "pending",
    gemini: "pending",
    grok: "pending",
    anthropic: "pending",
  });

  const connectionHealthy = true;
  const handleDemoLogin = () => {
    login({ email: "demo@integrityshield.ai", name: "Demo User" });
    navigate("/dashboard", { replace: true });
  };

  const handleSignIn = (event: React.FormEvent) => {
    event.preventDefault();
    const errors: typeof formErrors = {};
    if (!formState.email.trim()) {
      errors.email = "Email is required.";
    }
    if (!formState.password.trim()) {
      errors.password = "Password is required.";
    }
    setFormErrors(errors);
    if (Object.keys(errors).length === 0) {
      setCurrentStep(2);
    }
  };

  const handleProviderCheck = (providerId: string) => {
    setApiStatus((prev) => ({ ...prev, [providerId]: "checking" }));
    setTimeout(() => {
      setApiStatus((prev) => ({
        ...prev,
        [providerId]: apiKeys[providerId] ? "ready" : "pending",
      }));
    }, 500);
  };

  const handleComplete = () => {
    if (!formState.email.trim() || !formState.password.trim()) {
      setFormErrors({
        email: formState.email ? undefined : "Email is required.",
        password: formState.password ? undefined : "Password is required.",
      });
      setCurrentStep(1);
      return;
    }
    setSubmitting(true);
    setTimeout(() => {
      login({ email: formState.email, name: formState.name });
      navigate("/dashboard", { replace: true });
    }, 400);
  };

  const providerRows = useMemo(
    () =>
      API_PROVIDERS.map((provider) => {
        const status = apiStatus[provider.id];
        const configured = status === "ready";
        const checking = status === "checking";
        return {
          ...provider,
          configured,
          checking,
          statusLabel: configured ? "Ready" : checking ? "Checking…" : "Optional",
        };
      }),
    [apiStatus]
  );

  return (
    <PublicShell>
      <div className="wizard">
        <div className="wizard__steps">
          {steps.map((step) => (
            <div key={step.id} className={clsx("wizard-step", currentStep === step.id ? "is-active" : "", currentStep > step.id ? "is-complete" : "")}>
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
                <h2>Sign in</h2>
                <p>Use your IntegrityShield sandbox credentials.</p>
              </div>
              <Button as={Link} to="/" color="secondary" withBackground={false}>
                Back to Home
              </Button>
            </header>
            <form className="form-grid" onSubmit={handleSignIn}>
              <label>
                <span>Name</span>
                <input
                  type="text"
                  value={formState.name}
                  onChange={(event) => setFormState((prev) => ({ ...prev, name: event.target.value }))}
                  placeholder="Optional"
                />
              </label>
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
              </label>
              <div className="wizard-actions">
                <Button type="submit" color="primary">
                  Continue
                </Button>
                <Button type="button" color="secondary" withBackground={false} onClick={handleDemoLogin}>
                  Continue as demo user
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
                <p>Providers are optional. Add keys if you’d like IntegrityShield to run multi-provider evaluation comparisons.</p>
              </div>
            </header>

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
                      provider.configured ? "completed" : provider.checking ? "running" : "pending"
                    )}
                  >
                    {provider.statusLabel}
                  </span>
                </div>
                <input
                  type="text"
                  placeholder={`Enter your ${provider.label} API key`}
                  value={apiKeys[provider.id] ?? ""}
                  onChange={(event) => setApiKeys((prev) => ({ ...prev, [provider.id]: event.target.value }))}
                />
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
                    "Check"
                  )}
                </Button>
              </div>
            ))}
          </div>

            <footer className="wizard-footer">
              <div className="wizard-footer__note">You can revisit provider settings later in the tool.</div>
              <div className="wizard-footer__actions">
                <Button type="button" color="secondary" onClick={handleComplete} interaction={submitting ? "disabled" : "enabled"}>
                  Skip provider setup
                </Button>
                <Button type="button" color="primary" onClick={handleComplete} interaction={submitting ? "disabled" : "enabled"}>
                  {submitting ? <Loader2 className="spin" size={16} /> : null}
                  Continue to Dashboard
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
