import React from "react";
import { Lock, Save, User, Mail, Shield } from "lucide-react";
import { Button } from "@instructure/ui-buttons";
import { Text } from "@instructure/ui-text";
import { TextInput } from "@instructure/ui-text-input";

import LTIShell from "@layout/LTIShell";
import { PageSection } from "@components/layout/PageSection";
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
                Runs and saved credentials are scoped to this Canvas identity.
              </Text>
            </div>
          </div>
        </PageSection>

        {/* Provider Credentials Section */}
        <PageSection
          title="Provider credentials"
          subtitle="Managed centrally for now"
          actions={
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.25rem 0.75rem',
              backgroundColor: '#fff3e0',
              borderRadius: '0.375rem',
              border: '1px solid #ffe0b2'
            }}>
              <Lock size={14} color="#666666" />
              <Text size="x-small" color="secondary" weight="normal">Locked</Text>
            </div>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {/* Info Alert */}
            <div style={{
              padding: '0.75rem',
              backgroundColor: '#e8f4fd',
              borderRadius: '0.375rem',
              border: '1px solid #b3d9ff'
            }}>
              <Text size="small" color="secondary">
                Provider keys live in the backend for this sandbox. Frontend configuration and per-user storage will unlock in a later build.
              </Text>
            </div>

            {/* Provider Inputs */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {PROVIDERS.map((provider) => (
                <div key={provider.id}>
                  <TextInput
                    renderLabel={`${provider.label} API key`}
                    value="Managed in backend"
                    readOnly
                    interaction="disabled"
                  />
                </div>
              ))}
            </div>

            {/* Save Button (disabled) */}
            <div>
              <Button color="secondary" interaction="disabled">
                <Save size={16} /> Save (coming soon)
              </Button>
            </div>
          </div>
        </PageSection>
      </div>
    </LTIShell>
  );
};

export default SettingsLight;
