import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import Header from "@components/layout/Header";
import Sidebar from "@components/layout/Sidebar";
import Footer from "@components/layout/Footer";
import NotificationSystem from "@components/shared/NotificationSystem";
import ErrorBoundary from "@components/shared/ErrorBoundary";
import Dashboard from "@pages/Dashboard";
import RunDetail from "@pages/RunDetail";
import Settings from "@pages/Settings";
import DeveloperConsole from "@pages/DeveloperConsole";
import { PipelineProvider } from "@contexts/PipelineContext";
import { DeveloperProvider } from "@contexts/DeveloperContext";
import { NotificationProvider } from "@contexts/NotificationContext";
import PreviousRuns from "@pages/PreviousRuns";

const App: React.FC = () => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

  return (
    <NotificationProvider>
      <PipelineProvider>
        <DeveloperProvider>
          <ErrorBoundary>
            <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
              <Header />
              <div className="app-body" style={{ display: "flex", minHeight: "calc(100vh - 160px)" }}>
                <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((prev) => !prev)} />
                <main
                  style={{
                    flex: 1,
                    padding: "1.5rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "1.5rem",
                    transition: "margin-left 0.2s ease",
                  }}
                >
                  <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/runs" element={<PreviousRuns />} />
                    <Route path="/runs/:runId" element={<RunDetail />} />
                    <Route path="/settings" element={<Settings />} />
                    <Route path="/developer" element={<DeveloperConsole />} />
                    <Route path="*" element={<Navigate to="/dashboard" replace />} />
                  </Routes>
                </main>
              </div>
              <Footer />
              <NotificationSystem />
            </div>
          </ErrorBoundary>
        </DeveloperProvider>
      </PipelineProvider>
    </NotificationProvider>
  );
};

export default App;
