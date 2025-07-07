import React from 'react';

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
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>, setter: (f: File | null) => void) => {
    const file = e.target.files && e.target.files[0];
    setter(file ?? null);
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-sky-300 mb-1">Original Question Paper (PDF)</label>
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => handleFileSelect(e, onOriginalChange)}
          disabled={disabled}
          className="block w-full text-sm text-slate-100 file:bg-sky-700 file:border-0 file:py-2 file:px-4 file:rounded-md file:text-sm file:font-semibold hover:file:bg-sky-600"
        />
        {originalFile && <p className="text-xs mt-1">Selected: {originalFile.name}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-sky-300 mb-1">Answer Key (PDF)</label>
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => handleFileSelect(e, onAnswersChange)}
          disabled={disabled}
          className="block w-full text-sm text-slate-100 file:bg-sky-700 file:border-0 file:py-2 file:px-4 file:rounded-md file:text-sm file:font-semibold hover:file:bg-sky-600"
        />
        {answersFile && <p className="text-xs mt-1">Selected: {answersFile.name}</p>}
      </div>
    </div>
  );
}; 