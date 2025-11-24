import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

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
import { DemoRunProvider } from "@contexts/DemoRunContext";
import PreviousRuns from "@pages/PreviousRuns";
import ClassroomsPage from "@pages/Classrooms";
import ClassroomEvaluationPage from "@pages/ClassroomEvaluation";
import DetectionReportPage from "@pages/reports/DetectionReportPage";
import VulnerabilityReportPage from "@pages/reports/VulnerabilityReportPage";
import EvaluationReportPage from "@pages/reports/EvaluationReportPage";
import IntegrityShieldPipelineDemo from "@pages/IntegrityShieldPipelineDemo";

const App: React.FC = () => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);

  return (
    <NotificationProvider>
      <DemoRunProvider>
        <PipelineProvider>
          <DeveloperProvider>
            <ErrorBoundary>
              <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
                <div className="app-body" style={{ display: "flex", minHeight: "calc(100vh - 120px)" }}>
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
                      <Route path="/classrooms" element={<ClassroomsPage />} />
                      <Route path="/classrooms/:runId/:classroomId" element={<ClassroomEvaluationPage />} />
                      <Route path="/runs/:runId/reports/detection" element={<DetectionReportPage />} />
                      <Route path="/runs/:runId/reports/vulnerability" element={<VulnerabilityReportPage />} />
                      <Route path="/runs/:runId/reports/evaluation" element={<EvaluationReportPage />} />
                      <Route path="/demo/pipeline" element={<Navigate to="/demo/pipeline/ingestion" replace />} />
                      <Route path="/demo/pipeline/" element={<Navigate to="/demo/pipeline/ingestion" replace />} />
                      <Route path="/demo/pipeline/:stageId" element={<IntegrityShieldPipelineDemo />} />
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
      </DemoRunProvider>
    </NotificationProvider>
  );
};

export default App;
