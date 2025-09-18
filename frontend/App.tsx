import React, { useState, useCallback, useEffect } from 'react';
import { ControlPanel } from './components/ControlPanel';
import { LoadingSpinner } from './components/LoadingSpinner';
import { PdfUpload } from './components/PdfUpload';
import { DownloadLinks } from './components/DownloadLinks';
import { AttackType, AttackMode, PreventionSubType, AttackConfig } from './types';
import { uploadAssessment, fetchOriginalFile } from './services/assessmentService';
import { ExplorerModal } from './components/ExplorerModal';
import { useLocation } from 'react-router-dom';

const STORAGE_KEYS = {
  attack: 'fta_attack',
  lastAssessmentId: 'fta_last_assessment_id',
  runStatus: 'fta_run_status', // idle|running|completed
  attackMode: 'fta_attack_mode',
  preventionSubType: 'fta_prevention_sub_type',
  useNewSystem: 'fta_use_new_system',
};

const App: React.FC = () => {
  const location = useLocation() as { state?: { assessmentId?: string; attack_type?: string } };
  // New attack system state
  const [useNewSystem, setUseNewSystem] = useState<boolean>(() => {
    const saved = sessionStorage.getItem(STORAGE_KEYS.useNewSystem);
    return saved ? saved === 'true' : true; // Default to new system
  });
  const [attackMode, setAttackMode] = useState<AttackMode>(() => {
    const saved = sessionStorage.getItem(STORAGE_KEYS.attackMode) as AttackMode | null;
    return saved && Object.values(AttackMode).includes(saved) ? saved : AttackMode.DETECTION;
  });
  const [preventionSubType, setPreventionSubType] = useState<PreventionSubType>(() => {
    const saved = sessionStorage.getItem(STORAGE_KEYS.preventionSubType) as PreventionSubType | null;
    return saved && Object.values(PreventionSubType).includes(saved) ? saved : PreventionSubType.INVISIBLE_UNICODE;
  });

  // Legacy attack system state (backward compatibility)
  const [attack, setAttack] = useState<AttackType>(() => {
    const saved = sessionStorage.getItem(STORAGE_KEYS.attack) as AttackType | null;
    return saved && Object.values(AttackType).includes(saved) ? saved : AttackType.CODE_GLYPH;
  });
  const allowedAttacks: AttackType[] = [
    AttackType.CODE_GLYPH,
    AttackType.HIDDEN_MALICIOUS_INSTRUCTION_TOP,
    AttackType.HIDDEN_MALICIOUS_INSTRUCTION_PREVENTION,
    AttackType.NONE,
  ];

  const [originalPdf, setOriginalPdf] = useState<File | null>(null);
  const [answersPdf, setAnswersPdf] = useState<File | null>(null);
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [explorerOpen, setExplorerOpen] = useState(false);

  // State persistence effects
  useEffect(() => { sessionStorage.setItem(STORAGE_KEYS.attack, attack); }, [attack]);
  useEffect(() => { sessionStorage.setItem(STORAGE_KEYS.attackMode, attackMode); }, [attackMode]);
  useEffect(() => { sessionStorage.setItem(STORAGE_KEYS.preventionSubType, preventionSubType); }, [preventionSubType]);
  useEffect(() => { sessionStorage.setItem(STORAGE_KEYS.useNewSystem, useNewSystem.toString()); }, [useNewSystem]);

  useEffect(() => {
    const st = location.state;
    const run = async () => {
      try {
        const desiredAttack = st?.attack_type || sessionStorage.getItem(STORAGE_KEYS.attack);
        if (desiredAttack && Object.values(AttackType).includes(desiredAttack as AttackType)) setAttack(desiredAttack as AttackType);
        const persistedId = st?.assessmentId || sessionStorage.getItem(STORAGE_KEYS.lastAssessmentId);
        const runStatus = sessionStorage.getItem(STORAGE_KEYS.runStatus) || 'idle';
        if (persistedId) {
          setAssessmentId(persistedId);
          try {
            const file = await fetchOriginalFile(persistedId);
            setOriginalPdf(file);
          } catch {}
        }
        setIsLoading(runStatus === 'running');
      } catch (e: any) {
        setError(String(e.message || e));
      }
    };
    void run();
  }, [location.state]);

  const handleSubmit = useCallback(async () => {
    if (isLoading) return;
    if (!originalPdf) { setError('Please upload the question paper PDF. The answer key is optional.'); return; }
    setIsLoading(true);
    setError(null);
    setAssessmentId(null);
    sessionStorage.setItem(STORAGE_KEYS.runStatus, 'running');
    try {
      const clientId = sessionStorage.getItem(STORAGE_KEYS.lastAssessmentId) || crypto.randomUUID();
      const formData = new FormData();
      formData.append('original_pdf', originalPdf);
      if (answersPdf) formData.append('answers_pdf', answersPdf);
      formData.append('client_id', clientId);
      
      if (useNewSystem) {
        // New system: send attack_mode and prevention_sub_type
        formData.append('attack_mode', attackMode);
        if (attackMode === AttackMode.PREVENTION) {
          formData.append('prevention_sub_type', preventionSubType);
        }
      } else {
        // Legacy system: send attack_type
        formData.append('attack_type', attack);
      }
      const resp = await fetch('/api/assessments/upload', { method: 'POST', body: formData });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setAssessmentId(data.assessment_id);
      sessionStorage.setItem(STORAGE_KEYS.lastAssessmentId, data.assessment_id);
      sessionStorage.setItem(STORAGE_KEYS.runStatus, 'completed');
    } catch (err) {
      if (err instanceof Error) setError(err.message); else setError('An unexpected error occurred while uploading.');
      sessionStorage.setItem(STORAGE_KEYS.runStatus, 'idle');
    } finally {
      setIsLoading(false);
    }
  }, [originalPdf, answersPdf, attack, attackMode, preventionSubType, useNewSystem, isLoading]);

  const handleClear = () => {
    if (isLoading) return;
    setOriginalPdf(null);
    setAnswersPdf(null);
    setAssessmentId(null);
    setError(null);
    sessionStorage.removeItem(STORAGE_KEYS.lastAssessmentId);
    sessionStorage.removeItem(STORAGE_KEYS.runStatus);
  };

  return (
    <main className="container mx-auto px-4 py-8">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="flex flex-col space-y-6 p-6 bg-slate-850 rounded-xl shadow-2xl">
          <ControlPanel onSubmit={handleSubmit} onClear={handleClear} isLoading={isLoading} />
          {/* System Toggle */}
          <div>
            <label className="block text-sm font-medium text-sky-300 mb-1">Attack System</label>
            <div className="flex gap-3">
              <label className="inline-flex items-center gap-2">
                <input
                  type="radio"
                  checked={useNewSystem}
                  onChange={() => setUseNewSystem(true)}
                  disabled={isLoading}
                  className="accent-sky-600"
                />
                <span className="text-slate-100 text-sm">New (Prevention/Detection)</span>
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="radio"
                  checked={!useNewSystem}
                  onChange={() => setUseNewSystem(false)}
                  disabled={isLoading}
                  className="accent-sky-600"
                />
                <span className="text-slate-100 text-sm">Legacy</span>
              </label>
            </div>
          </div>

          {useNewSystem ? (
            <>
              {/* New Attack System UI */}
              <div>
                <label className="block text-sm font-medium text-sky-300 mb-1">Attack Mode</label>
                <select
                  value={attackMode}
                  onChange={(e) => setAttackMode(e.target.value as AttackMode)}
                  disabled={isLoading}
                  className="block w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600"
                >
                  <option value={AttackMode.DETECTION}>{AttackMode.DETECTION}</option>
                  <option value={AttackMode.PREVENTION}>{AttackMode.PREVENTION}</option>
                </select>
              </div>

              {attackMode === AttackMode.PREVENTION && (
                <div>
                  <label className="block text-sm font-medium text-sky-300 mb-1">Prevention Method</label>
                  <select
                    value={preventionSubType}
                    onChange={(e) => setPreventionSubType(e.target.value as PreventionSubType)}
                    disabled={isLoading}
                    className="block w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600"
                  >
                    <option value={PreventionSubType.INVISIBLE_UNICODE}>Invisible Unicode</option>
                    <option value={PreventionSubType.TINY_TEXT}>Tiny Text</option>
                    <option value={PreventionSubType.ACTUALTEXT_OVERRIDE}>ActualText Override</option>
                  </select>
                </div>
              )}

              {attackMode === AttackMode.DETECTION && (
                <div className="p-3 bg-slate-800 rounded-md">
                  <p className="text-xs text-slate-300">
                    <span className="font-semibold">Detection Strategy:</span> Per question, attempt Code Glyph (V3 entities → LLM validation → alternatives) → fallback to Hidden Text if all fail
                  </p>
                </div>
              )}
            </>
          ) : (
            /* Legacy Attack System UI */
            <div>
              <label className="block text-sm font-medium text-sky-300 mb-1">Attack Type (Legacy)</label>
              <select
                value={attack}
                onChange={(e) => setAttack(e.target.value as AttackType)}
                disabled={isLoading}
                className="block w-full bg-slate-800 text-slate-100 text-sm rounded-md border border-slate-700 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-600"
              >
                {allowedAttacks.map((a) => (<option key={a} value={a}>{a}</option>))}
              </select>
            </div>
          )}
          <PdfUpload originalFile={originalPdf} answersFile={answersPdf} onOriginalChange={(f) => { if (!isLoading) setOriginalPdf(f); }} onAnswersChange={(f) => { if (!isLoading) setAnswersPdf(f); }} disabled={isLoading} onOpenExplorer={() => setExplorerOpen(true)} />
        </div>

        <div className="flex flex-col space-y-6 p-6 bg-slate-850 rounded-xl shadow-2xl min-h-[360px]">
          {error && (
            <div className="p-4 bg-red-700 text-white rounded-md shadow-lg" role="alert">
              <h3 className="font-bold text-lg mb-1">Error</h3>
              <p className="text-sm">{error}</p>
            </div>
          )}
          {isLoading && (
            <div className="flex justify-center"><LoadingSpinner /></div>
          )}
          {assessmentId && !isLoading && !error && (
            <DownloadLinks assessmentId={assessmentId} />
          )}
          {!assessmentId && !isLoading && !error && (
            <div className="text-center text-slate-400 py-10"><p className="text-lg">Upload or pick a PDF and run the attack simulation.</p></div>
          )}
        </div>
      </div>
      <ExplorerModal open={explorerOpen} onClose={() => setExplorerOpen(false)} onSelectFile={(file) => { if (!isLoading) setOriginalPdf(file); }} />
    </main>
  );
};

export default App;