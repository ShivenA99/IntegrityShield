import React, { useState, useCallback } from 'react';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import { ControlPanel } from './components/ControlPanel';
import { LoadingSpinner } from './components/LoadingSpinner';
import { PdfUpload } from './components/PdfUpload';
import { DownloadLinks } from './components/DownloadLinks';
import { AttackType } from './types';
import { uploadAssessment } from './services/assessmentService';

const App: React.FC = () => {
  // Front-end no longer exposes attack selection – choose a fixed default that matches backend implementation
  const DEFAULT_ATTACK: AttackType = AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP;

  // File states
  const [originalPdf, setOriginalPdf] = useState<File | null>(null);
  const [answersPdf, setAnswersPdf] = useState<File | null>(null);

  // Backend response
  const [assessmentId, setAssessmentId] = useState<string | null>(null);

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

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
      const { assessment_id } = await uploadAssessment(originalPdf, answersPdf, DEFAULT_ATTACK);
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
  }, [originalPdf, answersPdf]);

  const handleClear = () => {
    setOriginalPdf(null);
    setAnswersPdf(null);
    setAssessmentId(null);
    setError(null);
    console.info('[handleClear] Cleared all state');
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-900 text-slate-100 font-sans">
      <Header />
      <main className="flex-grow container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Left Column: Controls and Input */}
          <div className="flex flex-col space-y-6 p-6 bg-slate-850 rounded-xl shadow-2xl">
            <ControlPanel
              onSubmit={handleSubmit}
              onClear={handleClear}
              isLoading={isLoading}
            />
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
      <Footer />
    </div>
  );
};

export default App;