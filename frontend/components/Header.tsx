import React from 'react';

export const Header: React.FC = () => {
  return (
    <header className="bg-slate-950 shadow-lg sticky top-0 z-50">
      <div className="container mx-auto px-4 py-4 md:py-5">
        <div className="flex flex-col md:flex-row justify-between items-center">
          <h1 className="text-2xl md:text-3xl font-bold text-sky-400 tracking-tight">
            FairTestAI
          </h1>
          <p className="text-sm md:text-base text-slate-300 mt-1 md:mt-0">
            LLM Assessment Vulnerability Simulator
          </p>
        </div>
      </div>
    </header>
  );
};
