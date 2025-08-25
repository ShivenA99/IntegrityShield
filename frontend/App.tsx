import React, { useState, useCallback } from 'react';
import { ControlPanel } from './components/ControlPanel';
import { LoadingSpinner } from './components/LoadingSpinner';
import { PdfUpload } from './components/PdfUpload';
import { DownloadLinks } from './components/DownloadLinks';
import { AttackType } from './types';
import { uploadAssessment } from './services/assessmentService';

const App: React.FC = () => {
  // Attack selection
  const [attack, setAttack] = useState<AttackType>(AttackType.CODE_GLYPH);
  const allowedAttacks: AttackType[] = [
    AttackType.CODE_GLYPH,
    AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP,
    AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION,
    AttackType.NONE,
  ];

  // File states
  const [originalPdf, setOriginalPdf] = useState<File | null>(null);
  const [answersPdf, setAnswersPdf] = useState<File | null>(null);

  // Backend response
  const [assessmentId, setAssessmentId] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // UI toggles (future backend integration)
  const [noCopy, setNoCopy] = useState(false);
  const [noScreenshot, setNoScreenshot] = useState(false);

  console.log('[App] Component mounted');

  const handleSubmit = useCallback(async () => {
    console.debug('[handleSubmit] Called');
    if (!originalPdf) {
      setError('Please upload the question paper PDF. The answer key is optional.');
      return;
    }

    setIsLoading(true);
    setError(null);
    setAssessmentId(null);

    try {
      const { assessment_id } = await uploadAssessment(originalPdf, answersPdf, attack);
      setAssessmentId(assessment_id);
    } catch (err) {
      console.error('[handleSubmit] uploadAssessment threw', err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred while uploading.');
      }
    } finally {
      setIsLoading(false);
    }
  }, [originalPdf, answersPdf, attack]);

  const handleClear = () => {
    setOriginalPdf(null);
    setAnswersPdf(null);
    setAssessmentId(null);
    setError(null);
    console.info('[handleClear] Cleared all state');
  };

  return (
    <main className="container mx-auto px-4 py-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Left Column: Controls and Input */}
        <div className="flex flex-col space-y-6 p-6 bg-slate-850 rounded-xl shadow-2xl">
          <ControlPanel
            onSubmit={handleSubmit}
            onClear={handleClear}
            isLoading={isLoading}
            noCopy={noCopy}
            noScreenshot={noScreenshot}
            onToggleNoCopy={setNoCopy}
            onToggleNoScreenshot={setNoScreenshot}
          />
          {/* Attack Type Dropdown */}
          <div>
            <label className="block text-sm font-medium text-sky-300 mb-1">Attack Type</label>
            <select
              value={attack}
              onChange={(e) => setAttack(e.target.value as AttackType)}
              disabled={isLoading}
              className="block w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600"
            >
              {allowedAttacks.map((a) => (
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
          <PdfUpload
            originalFile={originalPdf}
            answersFile={answersPdf}
            onOriginalChange={setOriginalPdf}
            onAnswersChange={setAnswersPdf}
            disabled={isLoading}
          />
        </div>

        {/* Right Column: Results */}
        <div className="flex flex-col space-y-6 p-6 bg-slate-850 rounded-xl shadow-2xl">
          {isLoading && <LoadingSpinner />}
          {error && (
            <div className="p-4 bg-red-700 text-white rounded-md shadow-lg" role="alert">
              <h3 className="font-bold text-lg mb-1">Error</h3>
              <p className="text-sm">{error}</p>
            </div>
          )}
          {assessmentId && !isLoading && !error && (
            <DownloadLinks assessmentId={assessmentId} />
          )}
          {!assessmentId && !isLoading && !error && (
            <div className="text-center text-slate-400 py-10">
              <p className="text-lg">Upload PDFs and run the attack simulation to see download links.</p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
};

export default App;