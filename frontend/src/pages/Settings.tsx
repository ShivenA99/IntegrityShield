import React, { useEffect, useState } from "react";
import { fetchSettings, updateSettings } from "@services/api/settingsApi";

const Settings: React.FC = () => {
  const [suffixBias, setSuffixBias] = useState<number | "">("");
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      try {
        const settings = await fetchSettings();
        if (!isMounted) return;
        setSuffixBias(settings.suffix_spacing_bias ?? "");
      } catch (err) {
        if (!isMounted) return;
        setError((err as Error)?.message ?? "Failed to load settings");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleBiasChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    if (value === "") {
      setSuffixBias("");
      return;
    }
    const numericValue = Number(value);
    if (!Number.isNaN(numericValue)) {
      setSuffixBias(numericValue);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (suffixBias === "" || Number.isNaN(Number(suffixBias))) {
      setError("Enter a numeric bias value");
      return;
    }
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await updateSettings({ suffix_spacing_bias: Number(suffixBias) });
      setSuffixBias(updated.suffix_spacing_bias ?? suffixBias);
      setMessage("Settings saved");
    } catch (err) {
      setError((err as Error)?.message ?? "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const previewPointsValue = typeof suffixBias === "number" ? (suffixBias / 1000) * 9 : 0;
  const previewPoints = previewPointsValue.toFixed(2);

  return (
    <div className="page settings">
      <h2>Settings</h2>
      <p>Adjust PDF reconstruction parameters. Values update immediately for new runs.</p>

      {loading ? (
        <p>Loading…</p>
      ) : (
        <form onSubmit={handleSubmit} className="settings-form">
          <label htmlFor="suffix-bias">
            Suffix Spacing Bias (text units)
            <input
              id="suffix-bias"
              type="number"
              step="1"
              value={suffixBias}
              onChange={handleBiasChange}
              disabled={saving}
              min={-5000}
              max={5000}
            />
          </label>
          <small>
            Roughly {previewPointsValue >= 0 ? previewPoints : `−${previewPoints.slice(1)}`} pt at 9&nbsp;pt text. Negative values move
            suffixes left; positive values move them right.
          </small>

          <button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>

          {message && <p className="settings-success">{message}</p>}
          {error && <p className="settings-error">{error}</p>}
        </form>
      )}
    </div>
  );
};

export default Settings;
