import React from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import NotificationSystem from "@components/shared/NotificationSystem";
import ErrorBoundary from "@components/shared/ErrorBoundary";
import Dashboard from "@pages/Dashboard";
import LoginPage from "@pages/LoginPage";
import LandingPage from "@pages/LandingPage";
import SettingsLight from "@pages/SettingsLight";
import HistoryPage from "@pages/HistoryPage";
import FilesPage from "@pages/FilesPage";
import ReportsPage from "@pages/ReportsPage";
import VideoPage from "@pages/VideoPage";
import { PipelineProvider } from "@contexts/PipelineContext";
import { DeveloperProvider } from "@contexts/DeveloperContext";
import { NotificationProvider } from "@contexts/NotificationContext";
import { DemoRunProvider } from "@contexts/DemoRunContext";
import { AuthProvider, useAuth } from "@contexts/AuthContext";

const RequireAuth: React.FC = () => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/try" replace />;
  }
  return <Outlet />;
};

const AppRoutes: React.FC = () => {
  const { isAuthenticated } = useAuth();
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/try" element={<LoginPage />} />
      <Route path="/login" element={<Navigate to="/try" replace />} />
      <Route path="/video" element={<VideoPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/files" element={<FilesPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsLight />} />
      </Route>
      <Route path="*" element={<Navigate to={isAuthenticated ? "/dashboard" : "/"} replace />} />
    </Routes>
  );
};

const App: React.FC = () => (
  <NotificationProvider>
    <DemoRunProvider>
      <PipelineProvider>
        <DeveloperProvider>
          <AuthProvider>
            <ErrorBoundary>
              <AppRoutes />
              <NotificationSystem />
            </ErrorBoundary>
          </AuthProvider>
        </DeveloperProvider>
      </PipelineProvider>
    </DemoRunProvider>
  </NotificationProvider>
);

export default App;
