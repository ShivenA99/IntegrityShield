import React from 'react';

export const SettingsPage: React.FC = () => {
  return (
    <main className="container mx-auto px-4 py-8">
      <h2 className="text-xl font-semibold mb-4">Settings</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="p-4 bg-slate-850 rounded border border-slate-800">
          <h3 className="font-medium mb-2">General</h3>
          <label className="flex items-center gap-2 opacity-60">
            <input type="checkbox" disabled className="accent-sky-600" />
            <span>Remember last filters</span>
          </label>
        </div>
        <div className="p-4 bg-slate-850 rounded border border-slate-800">
          <h3 className="font-medium mb-2">Rendering</h3>
          <label className="flex items-center gap-2 opacity-60">
            <input type="checkbox" disabled className="accent-sky-600" />
            <span>High-res overlay by default</span>
          </label>
        </div>
      </div>
      <p className="text-xs text-slate-400 mt-6">All settings are read-only in this version.</p>
    </main>
  );
}; 