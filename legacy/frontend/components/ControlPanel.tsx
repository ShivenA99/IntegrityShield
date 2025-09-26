import React from 'react';

interface ControlPanelProps {
  onSubmit: () => void;
  onClear: () => void;
  isLoading: boolean;
  noCopy?: boolean;
  noScreenshot?: boolean;
  onToggleNoCopy?: (v: boolean) => void;
  onToggleNoScreenshot?: (v: boolean) => void;
}

export const ControlPanel: React.FC<ControlPanelProps> = ({ onSubmit, onClear, isLoading, noCopy = false, noScreenshot = false, onToggleNoCopy, onToggleNoScreenshot }) => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row space-y-3 sm:space-y-0 sm:space-x-4">
        <button
          onClick={onSubmit}
          disabled={isLoading}
          className="w-full sm:w-auto flex-grow px-6 py-3 bg-sky-600 text-white font-semibold rounded-lg shadow-md hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2 focus:ring-offset-slate-800 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Processing...' : 'Test with LLM'}
        </button>
        <button
          onClick={onClear}
          disabled={isLoading}
          className="w-full sm:w-auto px-6 py-3 bg-slate-600 text-white font-semibold rounded-lg shadow-md hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-500 focus:ring-offset-2 focus:ring-offset-slate-800 transition duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Clear All
        </button>
      </div>

      <div className="flex items-center gap-6 text-sm">
        <label className="inline-flex items-center gap-2 opacity-70" title="Coming soon">
          <input type="checkbox" checked={noCopy} onChange={(e) => onToggleNoCopy?.(e.target.checked)} disabled className="accent-sky-600" />
          <span>No-copy</span>
        </label>
        <label className="inline-flex items-center gap-2 opacity-70" title="Coming soon">
          <input type="checkbox" checked={noScreenshot} onChange={(e) => onToggleNoScreenshot?.(e.target.checked)} disabled className="accent-sky-600" />
          <span>No-screenshot</span>
        </label>
      </div>
    </div>
  );
};
