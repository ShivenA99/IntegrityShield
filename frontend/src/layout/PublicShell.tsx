import React from "react";
import { NavLink, useLocation } from "react-router-dom";
import { Button } from "@instructure/ui-buttons";
import { IconExternalLinkLine } from "@instructure/ui-icons";

const NAV_ITEMS = [
  { label: "Home", to: "/" },
  { label: "Video demo", to: "/video" },
  { label: "Code repository", href: "https://github.com/fairtest-ai", external: true },
  { label: "Try it", to: "/try" },
];

interface PublicShellProps {
  children: React.ReactNode;
  hideNav?: boolean;
}

/**
 * PublicShell - Simplified layout for public-facing pages
 * Uses custom CSS with Canvas/InstUI aesthetic
 */
const PublicShell: React.FC<PublicShellProps> = ({ children, hideNav }) => {
  const location = useLocation();

  return (
    <div className="public-shell">
      {!hideNav && (
        <header className="public-header">
          <div className="public-header__container">
            <div className="public-header__branding">
              <div className="public-header__logo">
                <img src="/IS_logo.png?v=3" alt="IntegrityShield Logo" className="logo-image" />
              </div>
              <h1 className="public-header__title">INTEGRITYSHIELD</h1>
            </div>

            <nav className="public-nav" role="navigation" aria-label="Main navigation">
              {NAV_ITEMS.map((item) => {
                if (item.external) {
                  return (
                    <Button
                      key={item.label}
                      href={item.href}
                      target="_blank"
                      rel="noreferrer"
                      color="secondary"
                      withBackground={false}
                      renderIcon={<IconExternalLinkLine />}
                      iconPlacement="end"
                      style={{
                        background: 'rgba(255, 255, 255, 0.15)',
                        color: '#ffffff',
                        border: '2px solid rgba(255, 255, 255, 0.7)',
                        fontWeight: 600,
                      }}
                    >
                      {item.label}
                    </Button>
                  );
                }
                const isActive = location.pathname === item.to;

                if (isActive) {
                  return (
                    <Button
                      key={item.label}
                      as={NavLink}
                      to={item.to}
                      color="secondary"
                      withBackground={true}
                      className="nav-button-active"
                      style={{
                        background: '#FFFFFF',
                        backgroundColor: '#FFFFFF',
                        color: '#8B3A00',
                        border: '3px solid #FFFFFF',
                        fontWeight: 800,
                        boxShadow: '0 6px 16px rgba(0, 0, 0, 0.4)',
                        padding: '0.625rem 1.5rem',
                      }}
                    >
                      {item.label}
                    </Button>
                  );
                }

                return (
                  <Button
                    key={item.label}
                    as={NavLink}
                    to={item.to}
                    color="secondary"
                    withBackground={false}
                    className="nav-button-inactive"
                    style={{
                      background: 'transparent',
                      color: 'rgba(255, 255, 255, 0.85)',
                      border: '2px solid rgba(255, 255, 255, 0.5)',
                      fontWeight: 500,
                    }}
                  >
                    {item.label}
                  </Button>
                );
              })}
            </nav>
          </div>
        </header>
      )}

      <main className="public-main">
        {children}
      </main>
    </div>
  );
};

export default PublicShell;
