import React, { useState } from 'react';
import { Link, NavLink } from 'react-router-dom';

const avatarDataUri = `data:image/svg+xml;utf8,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="72" height="72" viewBox="0 0 72 72">\
  <rect width="72" height="72" rx="36" fill="#1f2937"/>\
  <circle cx="36" cy="28" r="14" fill="#334155"/>\
  <rect x="14" y="44" width="44" height="16" rx="8" fill="#334155"/>\
  <text x="36" y="33" text-anchor="middle" font-size="14" fill="#94a3b8" font-family="Arial, Helvetica, sans-serif">U</text>\
</svg>'
)}`;

export const Header: React.FC = () => {
  const [open, setOpen] = useState(false);
  return (
    <header className="bg-slate-950 shadow-lg sticky top-0 z-50">
      <div className="container mx-auto px-4 py-4 md:py-5">
        <div className="flex items-center justify-between gap-4 relative">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-2xl md:text-3xl font-bold text-sky-400 tracking-tight">
              FairTestAI
            </Link>
            <nav className="hidden md:flex items-center gap-4 text-slate-300">
              <NavLink to="/" className={({ isActive }: { isActive: boolean }) => isActive ? 'text-sky-400' : 'hover:text-sky-300'}>Home</NavLink>
              <NavLink to="/uploads" className={({ isActive }: { isActive: boolean }) => isActive ? 'text-sky-400' : 'hover:text-sky-300'}>Uploads</NavLink>
              <span className="opacity-50 cursor-not-allowed" title="Coming soon">Evaluation</span>
              <NavLink to="/settings" className={({ isActive }: { isActive: boolean }) => isActive ? 'text-sky-400' : 'hover:text-sky-300'}>Settings</NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden md:inline text-sm text-slate-300">LLM Assessment Vulnerability Simulator</span>
            <div className="relative">
              <button type="button" className="w-9 h-9 rounded-full bg-slate-700 border border-slate-600 overflow-hidden" title="Profile" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
                <img src={avatarDataUri} alt="User" className="w-full h-full object-cover opacity-80" />
              </button>
              {open && (
                <div className="absolute right-0 mt-2 w-44 bg-slate-800 border border-slate-700 rounded-md shadow-lg z-50" role="menu" onMouseLeave={() => setOpen(false)}>
                  <div className="py-1 text-sm text-slate-200">
                    <button className="w-full text-left px-3 py-2 hover:bg-slate-700 opacity-60 cursor-not-allowed" disabled>Profile (soon)</button>
                    <button className="w-full text-left px-3 py-2 hover:bg-slate-700 opacity-60 cursor-not-allowed" disabled>Help / Docs</button>
                    <button className="w-full text-left px-3 py-2 hover:bg-slate-700 opacity-60 cursor-not-allowed" disabled>Sign out</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};
