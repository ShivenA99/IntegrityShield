import React, { useEffect, useState } from "react";
import { CheckCircle2, Loader2, Save, User, Mail, Shield, AlertCircle, Trash2 } from "lucide-react";
import { Button } from "@instructure/ui-buttons";
import { Text } from "@instructure/ui-text";

import LTIShell from "@layout/LTIShell";
import { PageSection } from "@components/layout/PageSection";
import { useAuth } from "@contexts/AuthContext";
import { apiClient } from "@services/api";

const PROVIDERS = [
  { id: "openai", label: "OpenAI" },
  { id: "gemini", label: "Gemini" },
  { id: "grok", label: "Grok" },
  { id: "anthropic", label: "Anthropic" },
];

const SettingsLight: React.FC = () => {
  const { user } = useAuth();
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiStatus, setApiStatus] = useState<Record<string, "pending" | "checking" | "ready" | "error">>({
    openai: "pending",
    gemini: "pending",
    grok: "pending",
    anthropic: "pending",
  });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load existing API keys on mount
  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      setLoading(true);
      const response = await apiClient.getApiKeys();
      // Note: API keys are not returned for security, only metadata
      // We'll mark them as configured if they exist
      const existingProviders = new Set(response.api_keys.map((k: any) => k.provider));
      setApiStatus((prev) => {
        const updated = { ...prev };
        existingProviders.forEach((provider) => {
          updated[provider] = "ready";
        });
        return updated;
      });
    } catch (error: any) {
      console.error("Failed to load API keys:", error);
      setError("Failed to load API keys");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyChange = (providerId: string, value: string) => {
    setApiKeys((prev) => ({ ...prev, [providerId]: value }));
    // Reset status if user is editing
    if (apiStatus[providerId] === "ready" || apiStatus[providerId] === "error") {
      setApiStatus((prev) => ({ ...prev, [providerId]: "pending" }));
    }
    setMessage(null);
    setError(null);
  };

  const handleValidate = async (providerId: string) => {
    const apiKey = apiKeys[providerId]?.trim();
    if (!apiKey) {
      setError("Please enter an API key first");
      return;
    }

    setApiStatus((prev) => ({ ...prev, [providerId]: "checking" }));
    try {
      const result = await apiClient.validateApiKey(providerId, apiKey);
      if (result.valid) {
        setApiStatus((prev) => ({ ...prev, [providerId]: "ready" }));
        setMessage(`${PROVIDERS.find(p => p.id === providerId)?.label} API key is valid`);
      } else {
        setApiStatus((prev) => ({ ...prev, [providerId]: "error" }));
        setError(result.message || "API key validation failed");
      }
    } catch (error: any) {
      setApiStatus((prev) => ({ ...prev, [providerId]: "error" }));
      setError(error.message || "Failed to validate API key");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      // Save all entered API keys
      const savePromises = Object.entries(apiKeys)
        .filter(([_, key]) => key.trim())
        .map(([provider, key]) => apiClient.saveApiKey(provider, key.trim()));

      await Promise.all(savePromises);
      setMessage("API keys saved successfully");
      
      // Reload to update status
      await loadApiKeys();
      
      // Clear the input fields after successful save
      setApiKeys({});
    } catch (error: any) {
      setError(error.message || "Failed to save API keys");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (providerId: string) => {
    try {
      await apiClient.deleteApiKey(providerId);
      setApiStatus((prev) => ({ ...prev, [providerId]: "pending" }));
      setMessage(`${PROVIDERS.find(p => p.id === providerId)?.label} API key deleted`);
      await loadApiKeys();
    } catch (error: any) {
      setError(error.message || "Failed to delete API key");
    }
  };

  const hasChanges = Object.keys(apiKeys).some(key => apiKeys[key].trim());

  return (
    <LTIShell title="Settings">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
        {/* Profile Section */}
        <PageSection title="Profile">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Profile Info Cards */}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem'
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                backgroundColor: '#f9f9f9',
                borderRadius: '0.5rem',
                border: '1px solid #e0e0e0'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '2rem',
                  height: '2rem',
                  backgroundColor: '#FF7F32',
                  borderRadius: '0.375rem',
                  flexShrink: 0
                }}>
                  <User size={16} color="#ffffff" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text size="x-small" color="secondary" weight="normal">Name</Text>
                  <div style={{ marginTop: '0.125rem' }}>
                    <Text size="small" weight="normal" style={{ color: '#333333' }}>
                      {user?.name ?? "Unknown"}
                    </Text>
                  </div>
                </div>
              </div>

              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                backgroundColor: '#f9f9f9',
                borderRadius: '0.5rem',
                border: '1px solid #e0e0e0'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '2rem',
                  height: '2rem',
                  backgroundColor: '#FF7F32',
                  borderRadius: '0.375rem',
                  flexShrink: 0
                }}>
                  <Mail size={16} color="#ffffff" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text size="x-small" color="secondary" weight="normal">Email</Text>
                  <div style={{ marginTop: '0.125rem' }}>
                    <Text size="small" weight="normal" style={{ color: '#333333' }}>
                      {user?.email ?? "—"}
                    </Text>
                  </div>
                </div>
              </div>

              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                padding: '0.75rem 1rem',
                backgroundColor: '#f9f9f9',
                borderRadius: '0.5rem',
                border: '1px solid #e0e0e0'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '2rem',
                  height: '2rem',
                  backgroundColor: '#FF7F32',
                  borderRadius: '0.375rem',
                  flexShrink: 0
                }}>
                  <Shield size={16} color="#ffffff" />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text size="x-small" color="secondary" weight="normal">Role</Text>
                  <div style={{ marginTop: '0.125rem' }}>
                    <Text size="small" weight="normal" style={{ color: '#333333' }}>
                      Instructor
                    </Text>
                  </div>
                </div>
              </div>
            </div>

            {/* Info Note */}
            <div style={{
              padding: '0.75rem',
              backgroundColor: '#f0f7ff',
              borderRadius: '0.375rem',
              border: '1px solid #b3d9ff'
            }}>
              <Text size="small" color="secondary">
                Runs and saved credentials are scoped to your account.
              </Text>
            </div>
          </div>
        </PageSection>

        {/* Provider Credentials Section */}
        <PageSection
          title="Provider credentials"
          subtitle="Manage your API keys for LLM providers"
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Messages */}
            {message && (
              <div style={{
                padding: '0.75rem',
                backgroundColor: '#e8f5e9',
                borderRadius: '0.375rem',
                border: '1px solid #a5d6a7',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <CheckCircle2 size={16} color="#4caf50" />
                <Text size="small" style={{ color: '#2e7d32' }}>{message}</Text>
              </div>
            )}

            {error && (
              <div style={{
                padding: '0.75rem',
                backgroundColor: '#ffebee',
                borderRadius: '0.375rem',
                border: '1px solid #ef9a9a',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem'
              }}>
                <AlertCircle size={16} color="#c62828" />
                <Text size="small" style={{ color: '#c62828' }}>{error}</Text>
              </div>
            )}

            {/* Info Alert */}
            <div style={{
              padding: '0.75rem',
              backgroundColor: '#e8f4fd',
              borderRadius: '0.375rem',
              border: '1px solid #b3d9ff'
            }}>
              <Text size="small" color="secondary">
                Add your API keys to enable multi-provider evaluation comparisons. Keys are encrypted and stored securely.
              </Text>
            </div>

            {/* Provider Inputs */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {PROVIDERS.map((provider) => {
                const status = apiStatus[provider.id];
                const isConfigured = status === "ready";
                const isChecking = status === "checking";
                const hasError = status === "error";
                const hasValue = apiKeys[provider.id]?.trim() || isConfigured;

                return (
                  <div key={provider.id} style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                          <label style={{ fontSize: '0.875rem', fontWeight: 500, color: '#333' }}>
                            {provider.label} API key
                          </label>
                          <input
                            type="password"
                            value={apiKeys[provider.id] || (isConfigured ? "••••••••••••••••" : "")}
                            onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                            placeholder={isConfigured ? "Key saved (enter new key to update)" : `Enter your ${provider.label} API key`}
                            disabled={loading}
                            style={{
                              padding: '0.5rem 0.75rem',
                              border: '1px solid #c7cdd1',
                              borderRadius: '0.375rem',
                              fontSize: '0.875rem',
                              width: '100%',
                              backgroundColor: loading ? '#f5f5f5' : '#fff',
                              cursor: loading ? 'not-allowed' : 'text'
                            }}
                          />
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-end' }}>
                        {hasValue && !isConfigured && (
                          <Button
                            color="secondary"
                            onClick={() => handleValidate(provider.id)}
                            interaction={isChecking ? "disabled" : "enabled"}
                          >
                            {isChecking ? (
                              <>
                                <Loader2 size={14} className="spin" /> Validate
                              </>
                            ) : hasError ? (
                              <>
                                <AlertCircle size={14} /> Retry
                              </>
                            ) : (
                              "Validate"
                            )}
                          </Button>
                        )}
                        {isConfigured && (
                          <Button
                            color="secondary"
                            onClick={() => handleDelete(provider.id)}
                            interaction="enabled"
                          >
                            <Trash2 size={14} /> Delete
                          </Button>
                        )}
                      </div>
                    </div>
                    {isConfigured && (
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        padding: '0.25rem 0.5rem',
                        backgroundColor: '#e8f5e9',
                        borderRadius: '0.25rem',
                        width: 'fit-content'
                      }}>
                        <CheckCircle2 size={12} color="#4caf50" />
                        <Text size="x-small" style={{ color: '#2e7d32' }}>Configured</Text>
                      </div>
                    )}
                    {hasError && (
                      <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        padding: '0.25rem 0.5rem',
                        backgroundColor: '#ffebee',
                        borderRadius: '0.25rem',
                        width: 'fit-content'
                      }}>
                        <AlertCircle size={12} color="#c62828" />
                        <Text size="x-small" style={{ color: '#c62828' }}>Invalid key</Text>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Save Button */}
            <div>
              <Button
                color="primary"
                onClick={handleSave}
                interaction={saving || !hasChanges ? "disabled" : "enabled"}
              >
                {saving ? (
                  <>
                    <Loader2 size={16} className="spin" /> Saving...
                  </>
                ) : (
                  <>
                    <Save size={16} /> Save API Keys
                  </>
                )}
              </Button>
            </div>
          </div>
        </PageSection>
      </div>
    </LTIShell>
  );
};

export default SettingsLight;
