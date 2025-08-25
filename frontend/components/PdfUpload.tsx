import React, { useCallback, useEffect, useState } from 'react';
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.mjs?url';

GlobalWorkerOptions.workerSrc = workerSrc as unknown as string;

interface PdfUploadProps {
  originalFile: File | null;
  answersFile: File | null;
  onOriginalChange: (file: File | null) => void;
  onAnswersChange: (file: File | null) => void;
  disabled?: boolean;
}

export const PdfUpload: React.FC<PdfUploadProps> = ({
  originalFile,
  answersFile,
  onOriginalChange,
  onAnswersChange,
  disabled = false,
}: PdfUploadProps) => {
  type Thumb = { page: number; url: string };
  const [originalThumbs, setOriginalThumbs] = useState<Thumb[]>([]);
  const [answersThumbs, setAnswersThumbs] = useState<Thumb[]>([]);

  const [overlayOpen, setOverlayOpen] = useState(false);
  const [overlayImg, setOverlayImg] = useState<string | null>(null);

  const renderPage = useCallback(async (arrayBuffer: ArrayBuffer, pageNum: number, scale = 1.2): Promise<string> => {
    const pdf = await getDocument({ data: arrayBuffer }).promise;
    const page = await pdf.getPage(pageNum);
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    if (!ctx) return '';
    await page.render({ canvasContext: ctx as any, viewport }).promise;
    return canvas.toDataURL('image/png');
  }, []);

  const renderAllPages = useCallback(async (file: File, setThumbs: (t: Thumb[]) => void) => {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await getDocument({ data: arrayBuffer }).promise;
    const total = pdf.numPages;
    const thumbs: Thumb[] = [];
    for (let i = 1; i <= total; i++) {
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
  }, []);

  const handleSetFile = useCallback(async (file: File | null, setter: (f: File | null) => void, setThumbs: (t: Thumb[]) => void) => {
    setter(file);
    if (file && file.type === 'application/pdf') {
      try {
        await renderAllPages(file, setThumbs);
      } catch {
        setThumbs([]);
      }
    } else {
      setThumbs([]);
    }
  }, [renderAllPages]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>, setter: (f: File | null) => void, setThumbs: (t: Thumb[]) => void) => {
    const file = e.target.files && e.target.files[0];
    void handleSetFile(file ?? null, setter, setThumbs);
  };

  const makeDropHandlers = (
    setter: (f: File | null) => void,
    setThumbs: (t: Thumb[]) => void,
  ) => ({
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
    },
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      if (disabled) return;
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file && file.type === 'application/pdf') {
        void handleSetFile(file, setter, setThumbs);
      }
    },
  });

  const openOverlay = useCallback(async (file: File | null, page: number) => {
    if (!file) return;
    const img = await renderPage(await file.arrayBuffer(), page, 1.5);
    setOverlayImg(img || null);
    setOverlayOpen(true);
  }, [renderPage]);

  // Clear thumbnails when parent clears files
  useEffect(() => {
    if (!originalFile) setOriginalThumbs([]);
  }, [originalFile]);
  useEffect(() => {
    if (!answersFile) setAnswersThumbs([]);
  }, [answersFile]);

  const DropZone: React.FC<{
    label: string;
    file: File | null;
    thumbs: Thumb[];
    onDropSet: ReturnType<typeof makeDropHandlers>;
    onChoose: (e: React.ChangeEvent<HTMLInputElement>) => void;
    onThumbClick: (page: number) => void;
  }> = ({ label, file, thumbs, onDropSet, onChoose, onThumbClick }) => (
    <div>
      <label className="block text-sm font-medium text-sky-300 mb-1">{label}</label>
      <div
        className="p-3 border border-dashed border-slate-600 rounded-md bg-slate-800 hover:border-sky-600"
        {...onDropSet}
      >
        <div className="flex items-start gap-3">
          <div className="flex-1">
            {thumbs.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 lg:grid-cols-5 gap-3">
                {thumbs.map((t) => (
                  <button
                    key={t.page}
                    type="button"
                    onClick={() => onThumbClick(t.page)}
                    className="relative block rounded border border-slate-600 bg-slate-700 overflow-hidden transform transition-transform duration-150 hover:scale-105 hover:ring-2 hover:ring-sky-500 hover:border-sky-500 focus:outline-none"
                    title={`Page ${t.page}`}
                    style={{ width: '7rem', height: '9.5rem' }}
                  >
                    <div className="w-full h-full">
                      <img
                        src={t.url}
                        alt={`Page ${t.page}`}
                        className="w-full h-full object-contain"
                      />
                    </div>
                    <span className="absolute bottom-1 right-1 text-[10px] bg-black/60 text-white px-1 rounded">{t.page}</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">Drag & drop a PDF here, or choose a file</p>
            )}
          </div>
          <div className="ml-auto">
            <label className="inline-block cursor-pointer px-2 py-1 text-xs bg-sky-700 hover:bg-sky-600 rounded-md text-white">
              Choose file
              <input
                type="file"
                accept="application/pdf"
                onChange={onChoose}
                disabled={disabled}
                className="hidden"
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <DropZone
        label="Original Question Paper (PDF)"
        file={originalFile}
        thumbs={originalThumbs}
        onDropSet={makeDropHandlers(onOriginalChange, setOriginalThumbs)}
        onChoose={(e) => handleFileSelect(e, onOriginalChange, setOriginalThumbs)}
        onThumbClick={(page) => openOverlay(originalFile, page)}
      />

      <DropZone
        label="Answer Key (PDF) (Optional)"
        file={answersFile}
        thumbs={answersThumbs}
        onDropSet={makeDropHandlers(onAnswersChange, setAnswersThumbs)}
        onChoose={(e) => handleFileSelect(e, onAnswersChange, setAnswersThumbs)}
        onThumbClick={(page) => openOverlay(answersFile, page)}
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