import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-slate-950 py-6 text-center mt-auto">
      <div className="container mx-auto px-4">
        <p className="text-sm text-slate-400">
          &copy; {new Date().getFullYear()} FairTestAI Simulator. For educational and research purposes.
        </p>
        <p className="text-xs text-slate-500 mt-1">
          This tool simulates prompt injection vulnerabilities in Large Language Models.
        </p>
      </div>
    </footer>
  );
};
