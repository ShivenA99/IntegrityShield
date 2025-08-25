import React from 'react';
import { AttackAnalysis } from '../types';

interface ResultsDisplayProps {
  originalText: string;
  modifiedText: string; // This text will have hidden characters visualized
  llmResponse: string;
  attackAnalysis: AttackAnalysis | null;
}

const ResultSection: React.FC<{ title: string; content: string; isCode?: boolean; customClasses?: string; 'aria-label'?: string }> = ({ title, content, isCode = false, customClasses = '', 'aria-label': ariaLabel }) => (
  <div className={`p-4 bg-slate-800 rounded-lg shadow-md ${customClasses}`} aria-labelledby={ariaLabel || title.toLowerCase().replace(/\s+/g, '-')}>
    <h3 id={ariaLabel || title.toLowerCase().replace(/\s+/g, '-')} className="text-lg font-semibold text-sky-400 mb-2 border-b border-slate-700 pb-1">{title}</h3>
    {isCode ? (
      <pre className="whitespace-pre-wrap break-all text-sm text-slate-200 bg-slate-700 p-3 rounded-md custom-scroll max-h-60 overflow-y-auto">
        {content || "No content to display."}
      </pre>
    ) : (
      <p className="text-sm text-slate-200 whitespace-pre-wrap break-words custom-scroll max-h-60 overflow-y-auto">
        {content || "No content to display."}
      </p>
    )}
  </div>
);


export const ResultsDisplay: React.FC<ResultsDisplayProps> = ({
  originalText,
  modifiedText,
  llmResponse,
  attackAnalysis,
}) => {
  return (
    <div className="space-y-6 max-h-[calc(100vh-200px)] overflow-y-auto custom-scroll pr-2" role="region" aria-label="Simulation Results">
      <style>{`
        .custom-scroll::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scroll::-webkit-scrollbar-track {
          background: #334155; /* slate-700 */
          border-radius: 10px;
        }
        .custom-scroll::-webkit-scrollbar-thumb {
          background: #0ea5e9; /* sky-500 */
          border-radius: 10px;
        }
        .custom-scroll::-webkit-scrollbar-thumb:hover {
          background: #0284c7; /* sky-600 */
        }
      `}</style>
      <ResultSection 
        title="Original Assessment Text (Human View)" 
        content={originalText}
        aria-label="original-assessment-text"
      />
      <ResultSection 
        title="Processed Text (LLM Input View - Hidden Elements Visualized)" 
        content={modifiedText} 
        isCode={true}
        customClasses="border-l-4 border-amber-500"
        aria-label="processed-text-llm-input"
      />
      <ResultSection 
        title="LLM Response" 
        content={llmResponse} 
        customClasses="border-l-4 border-green-500"
        aria-label="llm-response"
      />
      {attackAnalysis && (
        <div className="p-4 bg-slate-800 rounded-lg shadow-md border-l-4 border-purple-500 mt-4" role="region" aria-labelledby="attack-analysis-heading">
          <h3 id="attack-analysis-heading" className="text-lg font-semibold text-sky-400 mb-3 border-b border-slate-700 pb-2">
            Attack Vulnerability Analysis
          </h3>
          <div className="space-y-3">
            <div>
              <h4 className="text-md font-semibold text-slate-200 mb-1">Estimated Success Rate:</h4>
              <p className="text-sm text-slate-300 bg-slate-700 p-2 rounded-md">{attackAnalysis.successRate}</p>
            </div>
            <div>
              <h4 className="text-md font-semibold text-slate-200 mb-1">Vulnerability Deep Dive:</h4>
              <p className="text-sm text-slate-300 whitespace-pre-wrap break-words bg-slate-700 p-2 rounded-md max-h-60 overflow-y-auto custom-scroll">
                {attackAnalysis.vulnerabilityAnalysis}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};