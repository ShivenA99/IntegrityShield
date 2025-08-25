import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import { UploadsPage } from './pages/UploadsPage';
import { RootLayout } from './pages/RootLayout';
import { SettingsPage } from './pages/SettingsPage';

const root = document.getElementById('root');
if (!root) throw new Error('Could not find root element to mount to');

const rootEl = ReactDOM.createRoot(root);
rootEl.render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<RootLayout />}>
          <Route path="/" element={<App />} />
          <Route path="/uploads" element={<UploadsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
