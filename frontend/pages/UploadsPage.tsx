import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { listAssessments, AssessmentListItem } from '../services/assessmentService';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url';
import { AttackType } from '../types';

GlobalWorkerOptions.workerSrc = workerSrc as unknown as string;

type ThumbMap = Record<string, string>; // id -> dataUrl

type SortKey = 'created_at' | 'attack_type' | 'original_filename' | 'status';

type Order = 'asc' | 'desc';

const PAGE_SIZE = 10;

export const UploadsPage: React.FC = () => {
  const [items, setItems] = useState<AssessmentListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [q, setQ] = useState('');
  const [search, setSearch] = useState(''); // debounced input
  const [attackType, setAttackType] = useState<string>('');
  const [start, setStart] = useState<string>('');
  const [end, setEnd] = useState<string>('');
  const [sort, setSort] = useState<SortKey>('created_at');
  const [order, setOrder] = useState<Order>('desc');

  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  const [thumbs, setThumbs] = useState<ThumbMap>({});
  const [overlayImg, setOverlayImg] = useState<string | null>(null);

  // Debounce search input -> q
  useEffect(() => {
    const id = setTimeout(() => { setPage(1); setQ(search.trim()); }, 400);
    return () => clearTimeout(id);
  }, [search]);

  const params = useMemo(
    () => ({ q, attack_type: attackType || undefined, start: start || undefined, end: end || undefined, sort, order, page, page_size: PAGE_SIZE }),
    [q, attackType, start, end, sort, order, page]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listAssessments(params)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotalPages(res.pagination.total_pages);
        setTotalCount(res.pagination.total);
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [params]);

  const fetchArrayBuffer = useCallback(async (url: string): Promise<ArrayBuffer> => {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Fetch failed: ${res.status}`);
    const blob = await res.blob();
    return await blob.arrayBuffer();
  }, []);

  const renderPageImage = useCallback(async (data: ArrayBuffer, pageNum: number, scale = 1.5): Promise<string> => {
    const pdf = await getDocument({ data }).promise;
    try {
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      if (!ctx) return '';
      await page.render({ canvasContext: ctx as any, viewport }).promise;
      return canvas.toDataURL('image/png');
    } finally {
      try { (pdf as any).destroy?.(); } catch {}
    }
  }, []);

  const makeFirstPageThumb = useCallback(async (id: string, url: string) => {
    try {
      const data = await fetchArrayBuffer(url);
      const img = await renderPageImage(data, 1, 0.4);
      if (!img) return;
      setThumbs((prev) => (prev[id] ? prev : { ...prev, [id]: img }));
    } catch {
      // ignore thumb failure
    }
  }, [fetchArrayBuffer, renderPageImage]);

  useEffect(() => {
    items.forEach((it) => {
      if (!thumbs[it.id]) void makeFirstPageThumb(it.id, it.downloads.original);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  const openOverlayFull = useCallback(async (url: string) => {
    try {
      const data = await fetchArrayBuffer(url);
      const img = await renderPageImage(data, 1, 1.6);
      setOverlayImg(img || null);
    } catch {
      setOverlayImg(null);
    }
  }, [fetchArrayBuffer, renderPageImage]);

  const Pagination: React.FC = () => {
    const startIdx = totalCount === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
    const endIdx = Math.min(page * PAGE_SIZE, totalCount);
    return (
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2 mt-4">
        <span className="text-xs text-slate-400">Showing {startIdx}–{endIdx} of {totalCount}</span>
        <div className="flex items-center justify-center gap-2">
          <button
            className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
          >
            ‹ Prev
          </button>
          <span className="text-slate-300 text-sm">Page {page} of {totalPages}</span>
          <button
            className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
          >
            Next ›
          </button>
        </div>
      </div>
    );
  };

  const clearFilters = () => {
    setAttackType('');
    setStart('');
    setEnd('');
    setSort('created_at');
    setOrder('desc');
    setPage(1);
  };

  const handleSortHeader = (col: SortKey) => {
    if (sort === col) {
      setOrder((o) => (o === 'asc' ? 'desc' : 'asc'));
    } else {
      setSort(col);
      setOrder('asc');
    }
    setPage(1);
  };

  const sortIndicator = (col: SortKey) => sort === col ? (order === 'asc' ? ' ▲' : ' ▼') : '';

  const activeChips = (
    <div className="flex flex-wrap gap-2 mt-2">
      {attackType && (
        <button className="px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded" onClick={() => setAttackType('')}>
          Attack: {attackType} ×
        </button>
      )}
      {start && (
        <button className="px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded" onClick={() => setStart('')}>
          Start: {new Date(start).toLocaleString()} ×
        </button>
      )}
      {end && (
        <button className="px-2 py-1 text-xs bg-slate-800 border border-slate-700 rounded" onClick={() => setEnd('')}>
          End: {new Date(end).toLocaleString()} ×
        </button>
      )}
      {(attackType || start || end) && (
        <button className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 rounded" onClick={clearFilters}>
          Clear all
        </button>
      )}
    </div>
  );

  const SkeletonRows = (
    <tbody>
      {Array.from({ length: 5 }).map((_, i) => (
        <tr key={i} className="border-t border-slate-800 animate-pulse">
          <td className="py-3 pr-4">
            <div className="w-[5.5rem] h-[7.5rem] bg-slate-800 rounded" />
          </td>
          <td className="py-3 pr-4"><div className="h-4 w-40 bg-slate-800 rounded" /></td>
          <td className="py-3 pr-4"><div className="h-4 w-24 bg-slate-800 rounded" /></td>
          <td className="py-3 pr-4"><div className="h-4 w-32 bg-slate-800 rounded" /></td>
          <td className="py-3 pr-4"><div className="h-8 w-48 bg-slate-800 rounded" /></td>
        </tr>
      ))}
    </tbody>
  );

  return (
    <main className="container mx-auto px-4 py-8">
      <div className="flex flex-col gap-4 mb-6">
        <h2 className="text-xl font-semibold">Uploads</h2>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
          <div className="md:col-span-3">
            <label className="text-xs text-slate-400 mb-1 block">Search</label>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filename contains..."
              className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600"
            />
          </div>
          <div className="md:col-span-3">
            <label className="text-xs text-slate-400 mb-1 block">Attack</label>
            <select value={attackType} onChange={(e) => { setPage(1); setAttackType(e.target.value); }} className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 h-10">
              <option value="">All Attacks</option>
              {Object.values(AttackType).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-slate-400 mb-1 block">Start</label>
            <input type="datetime-local" value={start} onChange={(e) => { setPage(1); setStart(e.target.value); }} className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 h-10" />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-slate-400 mb-1 block">End</label>
            <input type="datetime-local" value={end} onChange={(e) => { setPage(1); setEnd(e.target.value); }} className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 h-10" />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs text-slate-400 mb-1 block">Sort by</label>
            <select value={sort} onChange={(e) => { setPage(1); setSort(e.target.value as SortKey); }} className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 h-10">
              <option value="created_at">Date created</option>
              <option value="original_filename">Filename</option>
              <option value="attack_type">Attack type</option>
            </select>
          </div>
          <div className="md:col-span-1">
            <label className="text-xs text-slate-400 mb-1 block">Order</label>
            <select value={order} onChange={(e) => { setPage(1); setOrder(e.target.value as Order); }} className="w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 h-10">
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>
          <div className="md:col-span-1 flex items-end">
            <button
              className="w-full px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-md text-sm"
              onClick={clearFilters}
            >
              Reset
            </button>
          </div>
        </div>
        {activeChips}
      </div>

      {error && <p className="text-red-400">{error}</p>}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-slate-300">
              <th className="py-2 pr-4 sticky top-0 bg-slate-900 z-10">Thumbnail</th>
              <th className="py-2 pr-4 sticky top-0 bg-slate-900 z-10 cursor-pointer select-none" onClick={() => handleSortHeader('original_filename')}>
                Original{sortIndicator('original_filename')}
              </th>
              <th className="py-2 pr-4 sticky top-0 bg-slate-900 z-10 cursor-pointer select-none" onClick={() => handleSortHeader('attack_type')}>
                Attack Type{sortIndicator('attack_type')}
              </th>
              <th className="py-2 pr-4 sticky top-0 bg-slate-900 z-10 cursor-pointer select-none" onClick={() => handleSortHeader('created_at')}>
                Created{sortIndicator('created_at')}
              </th>
              <th className="py-2 pr-4 sticky top-0 bg-slate-900 z-10">Downloads</th>
            </tr>
          </thead>
          {loading ? (
            SkeletonRows
          ) : (
            <tbody>
              {items.map((it) => (
                <tr key={it.id} className="border-t border-slate-800 hover:bg-slate-800/60">
                  <td className="py-2 pr-4">
                    <button
                      type="button"
                      className="relative block rounded border border-slate-600 bg-slate-700 overflow-hidden transform transition-transform duration-150 hover:scale-105 hover:ring-2 hover:ring-sky-500 hover:border-sky-500 focus:outline-none"
                      style={{ width: '5.5rem', height: '7.5rem' }}
                      title="Open original preview"
                      onClick={() => openOverlayFull(it.downloads.original)}
                    >
                      {thumbs[it.id] ? (
                        <img src={thumbs[it.id]} alt="thumb" className="w-full h-full object-contain" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-xs text-slate-400">Generating…</div>
                      )}
                    </button>
                  </td>
                  <td className="py-2 pr-4">{it.original_filename ?? '—'}</td>
                  <td className="py-2 pr-4">
                    <span className="inline-block px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-xs">{it.attack_type}</span>
                  </td>
                  <td className="py-2 pr-4">{new Date(it.created_at).toLocaleString()}</td>
                  <td className="py-2 pr-4">
                    <div className="flex gap-2">
                      <a className="px-2 py-1 bg-slate-700 rounded hover:bg-slate-600 inline-flex items-center gap-1" href={it.downloads.original} title="Download original PDF">
                        <span className="text-xs">⬇</span>
                        <span>Original</span>
                      </a>
                      <a className="px-2 py-1 bg-emerald-700 rounded hover:bg-emerald-600 inline-flex items-center gap-1" href={it.downloads.attacked} title="Download attacked PDF">
                        <span className="text-xs">⬇</span>
                        <span>Attacked</span>
                      </a>
                      <a className="px-2 py-1 bg-indigo-700 rounded hover:bg-indigo-600 inline-flex items-center gap-1" href={it.downloads.report} title="Download reference report">
                        <span className="text-xs">⬇</span>
                        <span>Report</span>
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          )}
        </table>
        <Pagination />
      </div>

      {overlayImg && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={() => setOverlayImg(null)}>
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="absolute -top-3 -right-3 bg-white text-black rounded-full w-7 h-7 font-bold"
              onClick={() => setOverlayImg(null)}
              aria-label="Close preview"
            >
              ×
            </button>
            <img src={overlayImg} alt="Full preview" className="max-w-full max-h-[90vh] rounded shadow-2xl" />
            <div className="flex justify-end mt-2">
              <a href="#" onClick={(e) => e.preventDefault()} className="text-xs text-slate-300 opacity-70 cursor-not-allowed" title="Coming soon">Open full PDF</a>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}; 