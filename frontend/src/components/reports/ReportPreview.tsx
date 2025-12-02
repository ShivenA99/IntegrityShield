import React, { useEffect, useState, useMemo, useCallback } from "react";
import { SummaryCard, ProviderBadge, OptionCard, MappingCard } from "@components/reports";

interface ReportPreviewProps {
  reportType: "vulnerability" | "detection" | "evaluation";
  fileUrl: string;
  mode?: string;
}

type QuestionOption = { label: string; text: string };

// Standard provider ordering - OpenAI, Claude, Gemini, Grok, then others alphabetically
const PROVIDER_ORDER = ["openai", "anthropic", "claude", "google", "gemini", "xai", "grok"];

const getProviderSortKey = (providerName: string): number => {
  const normalized = providerName.toLowerCase();
  for (let i = 0; i < PROVIDER_ORDER.length; i++) {
    if (normalized.includes(PROVIDER_ORDER[i])) {
      return i;
    }
  }
  return 999; // Unknown providers go to the end
};

const sortProviders = <T extends { provider: string }>(providers: T[]): T[] => {
  return [...providers].sort((a, b) => {
    const keyA = getProviderSortKey(a.provider);
    const keyB = getProviderSortKey(b.provider);
    if (keyA !== keyB) return keyA - keyB;
    // If same order key, sort alphabetically
    return a.provider.localeCompare(b.provider);
  });
};

const normalizeOptions = (rawOptions: any): QuestionOption[] => {
  if (!rawOptions) return [];
  if (Array.isArray(rawOptions)) {
    return rawOptions
      .map((entry, idx) => {
        if (typeof entry !== "object" || entry === null) {
          const fallbackLabel = String.fromCharCode(65 + idx);
          return { label: fallbackLabel, text: String(entry) };
        }
        const baseLabel =
          (entry.label ?? entry.option ?? entry.id ?? String.fromCharCode(65 + idx)) as string;
        const normalizedLabel = baseLabel ? baseLabel.toString().trim().toUpperCase() : String.fromCharCode(65 + idx);
        const text = (entry.text ?? entry.value ?? entry.content ?? "") as string;
        return { label: normalizedLabel, text: text.trim() };
      })
      .filter((opt) => Boolean(opt.label));
  }
  if (typeof rawOptions === "object") {
    return Object.entries(rawOptions).map(([label, text]) => ({
      label: label.toString().trim().toUpperCase(),
      text: String(text ?? "").trim(),
    }));
  }
  return [];
};

const inferAnswerLabel = (answer: string | null | undefined, options: QuestionOption[]): string | null => {
  if (!answer) return null;
  const stripped = answer.replace(/\*\*/g, "").trim();
  const directMatch = stripped.match(/([A-Z])[\).:\-]/i);
  if (directMatch) return directMatch[1].toUpperCase();
  const normalizedAnswer = stripped.toLowerCase();
  for (const option of options) {
    if (!option.text) continue;
    const normalizedOption = option.text.toLowerCase();
    if (normalizedAnswer === normalizedOption) return option.label;
    if (normalizedOption && normalizedAnswer.includes(normalizedOption)) return option.label;
  }
  return null;
};

const ReportPreview: React.FC<ReportPreviewProps> = ({ reportType, fileUrl, mode }) => {
  const [reportData, setReportData] = useState<Record<string, any> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedOptions, setExpandedOptions] = useState<Set<number>>(new Set());

  const toggleOptions = (questionNumber: number) => {
    setExpandedOptions((prev) => {
      const next = new Set(prev);
      if (next.has(questionNumber)) {
        next.delete(questionNumber);
      } else {
        next.add(questionNumber);
      }
      return next;
    });
  };

  useEffect(() => {
    const fetchReport = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(fileUrl);
        if (!response.ok) {
          throw new Error(`Failed to load: ${response.status}`);
        }
        const json = await response.json();
        setReportData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setIsLoading(false);
      }
    };
    fetchReport();
  }, [fileUrl]);

  const sortedQuestions = useMemo(() => {
    const questions = (reportData?.questions as any[]) || [];
    return [...questions].sort((a, b) => {
      const left = Number(a?.question_number ?? a?.questionNumber ?? 0);
      const right = Number(b?.question_number ?? b?.questionNumber ?? 0);
      return left - right;
    });
  }, [reportData]);

  if (isLoading) {
    return <div className="report-loading" style={{ padding: "2rem" }}><p>Loading report…</p></div>;
  }

  if (error) {
    return <div className="report-empty-state" style={{ padding: "2rem" }}><h3>Error Loading Report</h3><p>{error}</p></div>;
  }

  if (!reportData) {
    return <div className="report-empty-state" style={{ padding: "2rem" }}><h3>No Data</h3><p>Report data not available.</p></div>;
  }

  // Vulnerability Report
  if (reportType === "vulnerability") {
    const providerSummary = sortProviders((reportData?.summary?.providers as any[]) || []);
    return (
      <div style={{ padding: "2rem" }}>
        <section className="report-summary-cards">
          {providerSummary.length ? (
            providerSummary.map((provider) => (
              <SummaryCard
                key={provider.provider}
                title={provider.provider}
                value={`${((provider.average_score ?? 0) * 100).toFixed(1)}%`}
                subtitle={`${provider.questions_evaluated ?? 0} questions`}
                icon={<ProviderBadge provider={provider.provider} size="large" />}
              />
            ))
          ) : (
            <SummaryCard
              title="Total Questions"
              value={reportData?.summary?.total_questions ?? 0}
              icon={<span style={{ fontSize: "2rem" }}>📊</span>}
            />
          )}
        </section>

        <section className="report-question-list">
          {sortedQuestions.map((question) => {
            const options = normalizeOptions(question.options);
            const isExpanded = expandedOptions.has(question.question_number);
            return (
              <article key={question.question_number} className="report-question-card">
                <div className="card-header">
                  <span className="question-number">Q{question.question_number}</span>
                  <span className="question-type">{question.question_type ?? "unknown"}</span>
                  {question.gold_answer && <span className="gold-badge">Gold: {question.gold_answer}</span>}
                </div>
                <p className="question-stem">{question.question_text}</p>
                {options.length > 0 && (
                  <>
                    <button
                      onClick={() => toggleOptions(question.question_number)}
                      className="options-toggle-btn"
                      style={{
                        background: 'none',
                        border: '1px solid #e0e0e0',
                        borderRadius: '0.375rem',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        color: '#FF7F32',
                        cursor: 'pointer',
                        marginBottom: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      <span style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}>▶</span>
                      {isExpanded ? 'Hide' : 'Show'} Options ({options.length})
                    </button>
                    {isExpanded && (
                      <div className="options-grid">
                        {options.map((option) => (
                          <OptionCard
                            key={`${question.question_number}-${option.label}`}
                            label={option.label}
                            text={option.text || "—"}
                            isCorrect={option.label === question.gold_answer}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
                <div className="provider-answers">
                  {sortProviders((question.answers as any[]) || []).map((answer) => {
                    const verdict = answer?.scorecard?.verdict;
                    const isCorrect = verdict?.toLowerCase() === "correct";
                    const inferredLabel = answer?.answer_label ?? inferAnswerLabel(answer?.answer, options);
                    return (
                      <div
                        key={`${question.question_number}-${answer.provider}`}
                        className="answer-chip"
                        data-correct={isCorrect}
                      >
                        <ProviderBadge provider={answer?.provider || "Unknown"} />
                        <div className="answer-content">
                          <span className="answer-label">{inferredLabel || "?"}</span>
                          <span className="verdict">
                            {verdict?.replace(/_/g, " ") || (answer?.success ? "pending" : "error")}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </section>
      </div>
    );
  }

  // Detection Report
  if (reportType === "detection") {
    const summary = reportData?.summary;
    return (
      <div style={{ padding: "2rem" }}>
        {summary && (
          <section className="detection-summary-dashboard">
            <SummaryCard
              title="Total Questions"
              value={summary.total_questions ?? sortedQuestions.length}
              icon={<span style={{ fontSize: "2.5rem" }}>📊</span>}
            />
            <SummaryCard
              title="With Mappings"
              value={summary.questions_with_mappings ?? 0}
              icon={<span style={{ fontSize: "2.5rem" }}>🎯</span>}
            />
          </section>
        )}

        <section className="report-question-list">
          {sortedQuestions.map((question) => {
            const options = normalizeOptions(question.options);
            const isExpanded = expandedOptions.has(question.question_number);
            const mappings = Array.isArray(question.mappings) ? question.mappings : [];
            const limitedMappings = mappings.slice(0, 3);
            const signalPhrase = question.target_answer?.signal?.phrase ?? null;
            return (
              <article
                key={question.question_number}
                className="report-question-card"
              >
                <div className="card-header">
                  <span className="question-number">Q{question.question_number}</span>
                </div>
                <p className="question-stem">{question.stem_text}</p>
                {options.length > 0 && (
                  <>
                    <button
                      onClick={() => toggleOptions(question.question_number)}
                      className="options-toggle-btn"
                      style={{
                        background: 'none',
                        border: '1px solid #e0e0e0',
                        borderRadius: '0.375rem',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        color: '#FF7F32',
                        cursor: 'pointer',
                        marginBottom: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      <span style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}>▶</span>
                      {isExpanded ? 'Hide' : 'Show'} Options ({options.length})
                    </button>
                    {isExpanded && (
                      <div className="options-grid">
                        {options.map((option) => (
                          <OptionCard
                            key={`${question.question_number}-${option.label}`}
                            label={option.label}
                            text={option.text || "—"}
                            isCorrect={option.label === question.gold_answer?.label}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
                <div className="target-info">
                  <span className="gold-answer">Gold: {question.gold_answer?.label ?? "—"}</span>
                  <span className="target-answer">
                    Target: {question.target_answer?.labels?.length
                      ? question.target_answer.labels.join(", ")
                      : "—"}
                  </span>
                  {signalPhrase && <span className="signal-phrase">📡 Signal: "{signalPhrase}"</span>}
                </div>
                {limitedMappings.length > 0 && (
                  <div className="mappings-grid">
                    {limitedMappings.map((mapping, index) => (
                      <MappingCard
                        key={mapping.id ?? index}
                        context={mapping.context ?? "stem"}
                        original={mapping.original ?? "—"}
                        replacement={mapping.replacement ?? "—"}
                        deviationScore={mapping.deviation_score}
                        validated={mapping.validated ?? false}
                      />
                    ))}
                  </div>
                )}
                {mappings.length > limitedMappings.length && (
                  <button className="show-more-btn">
                    +{mappings.length - limitedMappings.length} more mapping
                    {mappings.length - limitedMappings.length === 1 ? "" : "s"}
                  </button>
                )}
              </article>
            );
          })}
        </section>
      </div>
    );
  }

  // Evaluation Report
  if (reportType === "evaluation") {
    const providerSummary = sortProviders((reportData?.summary?.providers as any[]) || []);
    return (
      <div style={{ padding: "2rem" }}>
        <section className="provider-performance-grid">
          {providerSummary.map((entry) => {
            const delta = entry.average_delta_from_baseline ?? 0;
            const deltaClass = delta >= 0 ? "positive" : "negative";
            return (
              <div key={entry.provider} className="provider-performance-card">
                <div className="provider-header">
                  <ProviderBadge provider={entry.provider} />
                  <h4>{entry.provider}</h4>
                </div>
                <div className="performance-metrics">
                  <div className="metric">
                    <span className="metric-value">
                      {((entry.average_score ?? 0) * 100).toFixed(1)}%
                    </span>
                    <span className="metric-label">Accuracy</span>
                  </div>
                  <div className="metric">
                    <span className={`metric-value ${deltaClass}`}>
                      {delta >= 0 ? "+" : ""}
                      {(delta * 100).toFixed(1)}%
                    </span>
                    <span className="metric-label">Δ from Baseline</span>
                  </div>
                  <div className="metric">
                    <span className="metric-value">{entry.questions_evaluated ?? 0}</span>
                    <span className="metric-label">Questions</span>
                  </div>
                </div>
                {entry.hit_detection_target_count > 0 && (
                  <div className="detection-targets-alert">
                    ⚠️ Hit {entry.hit_detection_target_count} detection target
                    {entry.hit_detection_target_count > 1 ? "s" : ""}
                  </div>
                )}
              </div>
            );
          })}
        </section>

        <section className="report-question-list">
          {sortedQuestions.map((question) => {
            const options = normalizeOptions(question.options);
            const isExpanded = expandedOptions.has(question.question_number);
            const detectionTarget = question.detection_target?.labels || [];
            return (
              <article key={question.question_number} className="report-question-card">
                <div className="card-header">
                  <span className="question-number">Q{question.question_number}</span>
                  {detectionTarget.length > 0 && (
                    <span className="has-detection-target">🎯 Detection Target</span>
                  )}
                </div>
                <p className="question-stem">{question.question_text}</p>
                {options.length > 0 && (
                  <>
                    <button
                      onClick={() => toggleOptions(question.question_number)}
                      className="options-toggle-btn"
                      style={{
                        background: 'none',
                        border: '1px solid #e0e0e0',
                        borderRadius: '0.375rem',
                        padding: '0.5rem 1rem',
                        fontSize: '0.875rem',
                        color: '#FF7F32',
                        cursor: 'pointer',
                        marginBottom: '0.75rem',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      <span style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s ease' }}>▶</span>
                      {isExpanded ? 'Hide' : 'Show'} Options ({options.length})
                    </button>
                    {isExpanded && (
                      <div className="options-grid">
                        {options.map((opt) => (
                          <OptionCard
                            key={`${question.question_number}-${opt.label}`}
                            label={opt.label}
                            text={opt.text}
                            isCorrect={opt.label === question.gold_answer}
                          />
                        ))}
                      </div>
                    )}
                  </>
                )}
                <div className="answers-comparison">
                  {sortProviders((question.answers as any[]) || []).map((answer) => {
                    const scorecard = answer.scorecard || {};
                    const detectionHit =
                      answer.matches_detection_target ?? scorecard.hit_detection_target;
                    const delta = answer.delta_from_baseline;
                    const deltaClass = delta && delta >= 0 ? "positive" : "negative";
                    return (
                      <div
                        key={`${question.question_number}-${answer.provider}`}
                        className="provider-answer-card"
                        data-hit-target={detectionHit}
                      >
                        <div className="provider-header">
                          <ProviderBadge provider={answer.provider || "Unknown"} />
                          <span className="provider-name">{answer.provider || "Unknown"}</span>
                        </div>
                        <div className="answer-info">
                          <span className="answer-label">{answer.answer_label || "?"}</span>
                          {scorecard.score != null && (
                            <div className="scorecard">
                              <span className="score">{scorecard.score.toFixed(2)}</span>
                              {scorecard.verdict && (
                                <span className="verdict">{scorecard.verdict}</span>
                              )}
                            </div>
                          )}
                        </div>
                        {detectionHit && (
                          <div className="detection-hit-alert">⚠️ Hit detection target!</div>
                        )}
                        {delta != null && (
                          <div className={`delta ${deltaClass}`}>
                            Δ {delta >= 0 ? "+" : ""}
                            {(delta * 100).toFixed(1)}%
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </article>
            );
          })}
        </section>
      </div>
    );
  }

  return <div style={{ padding: "2rem" }}><p>Unknown report type: {reportType}</p></div>;
};

export default ReportPreview;
