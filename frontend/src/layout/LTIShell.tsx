import React from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { View } from "@instructure/ui-view";
import { Flex } from "@instructure/ui-flex";
import { Heading } from "@instructure/ui-heading";
import { Text } from "@instructure/ui-text";
import { Avatar } from "@instructure/ui-avatar";
import { Button } from "@instructure/ui-buttons";
import { usePipelineContext } from "@contexts/PipelineContext";
import {
  IconDashboardLine,
  IconClockLine,
  IconFolderLine,
  IconDocumentLine,
  IconSettingsLine,
} from "@instructure/ui-icons";

const TOOL_NAV = [
  { label: "Dashboard", to: "/dashboard", icon: IconDashboardLine },
  { label: "History", to: "/history", icon: IconClockLine },
  { label: "Files", to: "/files", icon: IconFolderLine },
  { label: "Settings", to: "/settings", icon: IconSettingsLine },
];

interface LTIShellProps {
  title: string;
  subtitle?: string;
  actionSlot?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * LTIShell - Professional Canvas-style layout for LTI tool pages
 *
 * Features:
 * - Top navigation bar with IntegrityShield branding
 * - Sidebar navigation with page links
 * - Responsive layout with proper spacing
 */
const LTIShell: React.FC<LTIShellProps> = ({ title, subtitle, actionSlot, children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { activeRunId, resetActiveRun } = usePipelineContext();

  const handleReset = () => {
    resetActiveRun();
    navigate('/dashboard');
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      minHeight: '100vh',
      backgroundColor: '#f5f5f5'
    }}>
      {/* Top Navigation Bar */}
      <header style={{
        backgroundColor: '#FF7F32',
        borderBottom: '1px solid #e0e0e0',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        flexShrink: 0
      }}>
        <div style={{ padding: '0.75rem 1.5rem', position: 'relative' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            {/* Logo and Brand - Centered */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{
                padding: '0.375rem 0.75rem',
                backgroundColor: '#ffffff',
                borderRadius: '0.375rem',
                display: 'inline-flex'
              }}>
                <Text color="brand" weight="bold" size="medium">
                  IS
                </Text>
              </div>
              <Heading level="h1" margin="0">
                <Text size="large" weight="normal" transform="uppercase" letterSpacing="expanded" color="primary-inverse">
                  IntegrityShield
                </Text>
              </Heading>
            </div>
          </div>

          {/* Reset Button and User Avatar - Absolute positioned to right */}
          <div style={{ position: 'absolute', top: '50%', right: '1.5rem', transform: 'translateY(-50%)', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {activeRunId && (
              <button
                onClick={handleReset}
                style={{
                  padding: '0.5rem 1rem',
                  backgroundColor: '#ffffff',
                  border: '2px solid #ffffff',
                  borderRadius: '0.375rem',
                  color: '#FF7F32',
                  fontWeight: 600,
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  fontFamily: 'inherit',
                  boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)'
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.backgroundColor = '#f0f0f0';
                  e.currentTarget.style.transform = 'translateY(-1px)';
                  e.currentTarget.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.15)';
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.backgroundColor = '#ffffff';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';
                }}
              >
                Reset
              </button>
            )}
            <Avatar name="User" size="x-small" />
          </div>
        </div>
      </header>

      {/* Main Content with Sidebar */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <aside style={{
          width: '14rem',
          backgroundColor: '#f9f9f9',
          borderRight: '1px solid #e0e0e0',
          boxShadow: '2px 0 4px rgba(0,0,0,0.05)',
          flexShrink: 0
        }}>
          <nav style={{ padding: '1rem 0' }} role="navigation" aria-label="Main navigation">
            {TOOL_NAV.map((item) => {
              const isSelected = location.pathname.startsWith(item.to);
              const IconComponent = item.icon;
              return (
                <NavLink
                  key={item.label}
                  to={item.to}
                  style={{ textDecoration: 'none', color: 'inherit' }}
                >
                  <div style={{
                    padding: '0.625rem 1rem',
                    marginBottom: '0.75rem',
                    backgroundColor: isSelected ? '#FF7F32' : 'transparent',
                    borderLeft: isSelected ? '4px solid #FF7F32' : 'none',
                    cursor: 'pointer',
                    transition: 'background-color 0.2s ease',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1.5rem'
                  }}>
                    <div style={{
                      width: '2rem',
                      height: '2rem',
                      borderRadius: '50%',
                      backgroundColor: isSelected ? 'rgba(255,255,255,0.2)' : 'transparent',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'background-color 0.2s ease'
                    }}>
                      <IconComponent
                        color={isSelected ? "primary-inverse" : undefined}
                        size="medium"
                      />
                    </div>
                    <Text
                      weight={isSelected ? "bold" : "normal"}
                      color={isSelected ? "primary-inverse" : undefined}
                    >
                      {item.label}
                    </Text>
                  </div>
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <main style={{
          flex: 1,
          overflow: 'auto',
          padding: '1.5rem 2rem',
          backgroundColor: '#ffffff'
        }}>
          {(title || subtitle || actionSlot) && (
            <header style={{
              marginBottom: '2rem',
              paddingBottom: '1rem',
              borderBottom: '1px solid #e0e0e0',
              textAlign: 'center'
            }}>
              {(title || subtitle) && (
                <div>
                  {title && (
                    <h2 style={{
                      margin: 0,
                      marginBottom: subtitle ? '0.25rem' : 0,
                      fontSize: '1.75rem',
                      fontWeight: '400',
                      color: '#333333',
                      letterSpacing: '-0.03em'
                    }}>
                      {title}
                    </h2>
                  )}
                  {subtitle && (
                    <Text color="secondary" size="small">
                      {subtitle}
                    </Text>
                  )}
                </div>
              )}
              {actionSlot && (
                <div style={{
                  position: 'absolute',
                  top: '1.5rem',
                  right: '2rem'
                }}>
                  {actionSlot}
                </div>
              )}
            </header>
          )}

          <div>{children}</div>
        </main>
      </div>
    </div>
  );
};

export default LTIShell;
