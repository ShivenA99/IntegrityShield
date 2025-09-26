import React, { useEffect, useState } from 'react';
import { fetchOriginalFile } from '../services/assessmentService';

interface ExplorerItem {
  name: string;
  type: 'folder'|'file';
  modified_at: string;
  size: number;
  path: string; // relative under assessments
}

interface ExplorerModalProps {
  open: boolean;
  onClose: () => void;
  onSelectFile: (file: File, assessmentId?: string) => void;
}

export const ExplorerModal: React.FC<ExplorerModalProps> = ({ open, onClose, onSelectFile }) => {
  const [path, setPath] = useState<string>('/');
  const [items, setItems] = useState<ExplorerItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<'tiles'|'list'>('tiles');
  const [selectedAssessmentId, setSelectedAssessmentId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    const usp = new URLSearchParams();
    usp.set('path', path);
    fetch(`/api/assessments/files/tree?${usp.toString()}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then((data) => {
        setItems(data.items || []);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [open, path]);

  const upOne = () => {
    if (path === '/') return;
    const parts = path.replace(/^\/+|\/+$/g, '').split('/');
    parts.pop();
    const next = parts.length ? `/${parts.join('/')}` : '/';
    setSelectedAssessmentId(null);
    setPath(next);
  };

  const handleOpen = (it: ExplorerItem) => {
    if (it.type === 'folder') {
      setSelectedAssessmentId(null);
      setPath(path === '/' ? `/${it.name}` : `${path}/${it.name}`);
      // if path goes to an assessment folder, record its id (folder name)
      try {
        const folder = (path === '/' ? it.name : it.name);
        // Basic heuristic: folders at root are assessment UUIDs
        if (path === '/') setSelectedAssessmentId(folder);
      } catch {}
    }
  };

  const handleSelect = async () => {
    if (!selectedAssessmentId) return;
    try {
      const file = await fetchOriginalFile(selectedAssessmentId);
      onSelectFile(file, selectedAssessmentId);
      onClose();
    } catch (e) {
      setError(String(e));
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="relative w-full max-w-5xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2 text-sm text-slate-300">
            <button className="px-2 py-1 bg-slate-800 rounded disabled:opacity-50" onClick={upOne} disabled={path === '/'}>Up</button>
            <span className="text-slate-500">Path:</span>
            <span className="font-mono">{path}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <button className={`px-2 py-1 rounded ${view==='tiles'?'bg-slate-700':'bg-slate-800 hover:bg-slate-700'}`} onClick={() => setView('tiles')}>Tiles</button>
            <button className={`px-2 py-1 rounded ${view==='list'?'bg-slate-700':'bg-slate-800 hover:bg-slate-700'}`} onClick={() => setView('list')}>Details</button>
            <button className="px-2 py-1 bg-slate-700 rounded" onClick={onClose}>Close</button>
          </div>
        </div>
        <div className="p-4 overflow-auto" style={{ maxHeight: '70vh' }}>
          {loading && <p className="text-slate-400">Loading...</p>}
          {error && <p className="text-red-400 text-sm">{error}</p>}
          {!loading && !error && view === 'tiles' && (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {items.map((it) => (
                <button key={it.path} className={`p-3 rounded border ${selectedAssessmentId && path==='/' && it.name===selectedAssessmentId? 'border-sky-500' : 'border-slate-700'} bg-slate-800 hover:border-sky-500 text-left`} onClick={() => handleOpen(it)}>
                  <div className="w-full h-24 bg-slate-700 rounded mb-2 flex items-center justify-center text-slate-300 text-sm">
                    {it.type === 'folder' ? '📁' : '📄'}
                  </div>
                  <div className="text-xs text-slate-200 truncate" title={it.name}>{it.name}</div>
                  <div className="text-[10px] text-slate-500">{new Date(it.modified_at).toLocaleString()}</div>
                </button>
              ))}
            </div>
          )}
          {!loading && !error && view === 'list' && (
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-slate-300">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Modified</th>
                  <th className="py-2 pr-4">Size</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.path} className="border-t border-slate-800 hover:bg-slate-800/60 cursor-pointer" onClick={() => handleOpen(it)}>
                    <td className="py-2 pr-4">{it.name}</td>
                    <td className="py-2 pr-4">{it.type}</td>
                    <td className="py-2 pr-4">{new Date(it.modified_at).toLocaleString()}</td>
                    <td className="py-2 pr-4">{it.size}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-end gap-2">
          <button className="px-3 py-2 bg-slate-700 rounded" onClick={onClose}>Cancel</button>
          <button className="px-3 py-2 bg-sky-700 rounded disabled:opacity-50" onClick={handleSelect} disabled={!selectedAssessmentId}>Select original</button>
        </div>
      </div>
    </div>
  );
}; 