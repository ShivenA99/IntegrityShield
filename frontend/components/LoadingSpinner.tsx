import React from 'react';

export const LoadingSpinner: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center p-10">
      <div className="animate-spin rounded-full h-16 w-16 border-t-4 border-b-4 border-sky-500"></div>
      <p className="mt-4 text-lg text-slate-300">Processing with LLM...</p>
    </div>
  );
};
