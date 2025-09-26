import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url';

GlobalWorkerOptions.workerSrc = workerSrc as unknown as string;

interface DownloadLinksProps {
  assessmentId: string;
}

type Thumb = { page: number; url: string };

export const DownloadLinks: React.FC<DownloadLinksProps> = ({ assessmentId }) => {
  const timestamp = useMemo(() => Date.now(), [assessmentId]);
  const attackedUrl = `/api/assessments/${assessmentId}/attacked?t=${timestamp}`;
  const evalReportUrl = `/api/assessments/${assessmentId}/evaluation_report?t=${timestamp}`;
  const reportUrl = `/api/assessments/${assessmentId}/report?t=${timestamp}`;

  const [attackedThumbs, setAttackedThumbs] = useState<Thumb[]>([]);
  const [evalReportThumbs, setEvalReportThumbs] = useState<Thumb[]>([]);
  const [reportThumbs, setReportThumbs] = useState<Thumb[]>([]);

  const [overlayOpen, setOverlayOpen] = useState(false);
  const [overlayImg, setOverlayImg] = useState<string | null>(null);

  const fetchPdfArrayBuffer = useCallback(async (url: string): Promise<ArrayBuffer> => {
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Failed to fetch PDF: ${res.status}`);
    const blob = await res.blob();
    return await blob.arrayBuffer();
  }, []);

  const renderPage = useCallback(async (arrayBuffer: ArrayBuffer, pageNum: number, scale = 1.2): Promise<string> => {
    const pdf = await getDocument({ data: arrayBuffer }).promise;
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
      // Ensure pdf is destroyed to free memory
      try { (pdf as any).destroy?.(); } catch {}
    }
  }, []);

  const renderAllPagesFromUrl = useCallback(async (url: string, setThumbs: (t: Thumb[]) => void, maxPages = 10) => {
    try {
      const arrayBuffer = await fetchPdfArrayBuffer(url);
      const pdf = await getDocument({ data: arrayBuffer }).promise;
      try {
        const total = pdf.numPages;
        const thumbs: Thumb[] = [];
        const limit = Math.min(total, maxPages);
        for (let i = 1; i <= limit; i++) {
          const page = await pdf.getPage(i);
          const viewport = page.getViewport({ scale: 0.5 });
          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          if (!ctx) continue;
          await page.render({ canvasContext: ctx as any, viewport }).promise;
          thumbs.push({ page: i, url: canvas.toDataURL('image/png') });
        }
        setThumbs(thumbs);
      } finally {
        try { (pdf as any).destroy?.(); } catch {}
      }
    } catch {
      setThumbs([]);
    }
  }, [fetchPdfArrayBuffer]);

  const openOverlayFromUrl = useCallback(async (url: string, page: number) => {
    try {
      const arrayBuffer = await fetchPdfArrayBuffer(url);
      const img = await renderPage(arrayBuffer, page, 1.5);
      setOverlayImg(img || null);
      setOverlayOpen(true);
    } catch {
      setOverlayOpen(false);
      setOverlayImg(null);
    }
  }, [fetchPdfArrayBuffer, renderPage]);

  // Load previews when assessmentId changes
  useEffect(() => {
    setAttackedThumbs([]);
    setReportThumbs([]);
    if (!assessmentId) return;
    void renderAllPagesFromUrl(attackedUrl, setAttackedThumbs);
    void renderAllPagesFromUrl(reportUrl, setReportThumbs);
  }, [assessmentId, attackedUrl, reportUrl, renderAllPagesFromUrl]);

  useEffect(() => {
    (async () => {
      try {
        // Reuse the existing helper to render thumbnails; it internally fetches and paginates
        await renderAllPagesFromUrl(evalReportUrl, setEvalReportThumbs);
      } catch (e) {
        console.error(e);
      }
    })();
  }, [evalReportUrl, fetchPdfArrayBuffer, renderAllPagesFromUrl]);

  const PreviewGrid: React.FC<{
    title: string;
    url: string;
    thumbs: Thumb[];
    emptyHint?: string;
  }> = ({ title, url, thumbs, emptyHint }) => (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-sky-300">{title}</h3>
        <a
          href={url}
          download
          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded-md text-xs text-white shadow"
        >
          Download
        </a>
      </div>
      <div className="p-3 border border-slate-700 rounded-md bg-slate-800">
        {thumbs.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-5 gap-3">
            {thumbs.map((t) => (
              <button
                key={t.page}
                type="button"
                onClick={() => openOverlayFromUrl(url, t.page)}
                className="relative block rounded border border-slate-600 bg-slate-700 overflow-hidden transform transition-transform duration-150 hover:scale-105 hover:ring-2 hover:ring-sky-500 hover:border-sky-500 focus:outline-none"
                title={`Page ${t.page}`}
                style={{ width: '7rem', height: '9.5rem' }}
              >
                <div className="w-full h-full">
                  <img src={t.url} alt={`Page ${t.page}`} className="w-full h-full object-contain" />
                </div>
                <span className="absolute bottom-1 right-1 text-[10px] bg-black/60 text-white px-1 rounded">{t.page}</span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-400">{emptyHint ?? 'Preview will appear here after processing.'}</p>
        )}
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      <PreviewGrid
        title="Attacked PDF"
        url={attackedUrl}
        thumbs={attackedThumbs}
        emptyHint="No preview available yet."
      />

      <PreviewGrid
        title="Evaluation Report"
        url={evalReportUrl}
        thumbs={evalReportThumbs}
        emptyHint="No evaluation report yet."
      />

      <PreviewGrid
        title="Reference Report"
        url={reportUrl}
        thumbs={reportThumbs}
        emptyHint="No preview available yet."
      />

      {overlayOpen && overlayImg && (
        <div
          className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
          onClick={() => setOverlayOpen(false)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="absolute -top-3 -right-3 bg-white text-black rounded-full w-7 h-7 font-bold"
              onClick={() => setOverlayOpen(false)}
              aria-label="Close preview"
            >
              ×
            </button>
            <img src={overlayImg} alt="Full preview" className="max-w-full max-h-[90vh] rounded shadow-2xl" />
          </div>
        </div>
      )}
    </div>
  );
}; 