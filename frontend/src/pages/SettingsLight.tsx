import React from "react";
import { Lock, Save } from "lucide-react";
import clsx from "clsx";
import { Button } from "@instructure/ui-buttons";

import LTIShell from "@layout/LTIShell";
import { useAuth } from "@contexts/AuthContext";

const PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
  { id: "grok", label: "Grok" },
  { id: "anthropic", label: "Anthropic" },
];

const SettingsLight: React.FC = () => {
  const { user } = useAuth();

  return (
    <LTIShell title="Settings" subtitle="Manage account information and provider credentials.">
      <div className="settings-grid">
        <section className="canvas-card">
          <h2>Profile</h2>
          <div className="light-settings-list">
            <div>
              <span>Name</span>
              <strong>{user?.name ?? "Unknown"}</strong>
            </div>
            <div>
              <span>Email</span>
              <strong>{user?.email ?? "—"}</strong>
            </div>
            <div>
              <span>Role</span>
              <strong>Instructor</strong>
            </div>
          </div>
          <p className="settings-hint">Runs and saved credentials are scoped to this Canvas identity.</p>
        </section>

        <section className="canvas-card">
          <div className="light-card__header">
            <div>
              <h2>Provider credentials</h2>
              <p>Managed centrally for now.</p>
            </div>
            <Lock size={22} aria-hidden="true" className="light-card__icon" />
          </div>
          <div className="callout">
            <p>Provider keys live in the backend for this sandbox. Frontend configuration and per-user storage will unlock in a later build.</p>
          </div>
          <form className="light-settings-form">
            {PROVIDERS.map((provider) => (
              <label key={provider.id} className="light-settings-field">
                <span>{provider.label} API key</span>
                <input type="text" value="Managed in backend" readOnly disabled />
              </label>
            ))}
            <Button type="button" color="secondary" interaction="disabled" display="block">
              <Save size={16} />
              Save (coming soon)
            </Button>
          </form>
        </section>
      </div>
    </LTIShell>
  );
};

export default SettingsLight;
