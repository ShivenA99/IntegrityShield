import * as React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { usePipeline } from "@hooks/usePipeline";
import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";
import type { ClassroomDataset, ClassroomCreationPayload } from "@services/types/pipeline";

interface ClassroomConfigState {
  totalStudents: number;
  cheatingRatePercent: number;
  llmSharePercent: number;
  partialCopyMinPercent: number;
  partialCopyMaxPercent: number;
  fullCopyProbabilityPercent: number;
  paraphraseProbabilityPercent: number;
  writeParquet: boolean;
}

const defaultConfig: ClassroomConfigState = {
  totalStudents: 100,
  cheatingRatePercent: 35,
  llmSharePercent: 60,
  partialCopyMinPercent: 40,
  partialCopyMaxPercent: 75,
  fullCopyProbabilityPercent: 45,
  paraphraseProbabilityPercent: 65,
  writeParquet: false,
};

const ClassroomManagerPanel: React.FC = () => {
  const {
    status,
    activeRunId,
    selectedClassroomId,
    setSelectedClassroomId,
    createClassroomDataset,
    deleteClassroomDataset,
    evaluateClassroom,
    setPreferredStage,
  } = usePipeline();

  const [formState, setFormState] = useState(() => ({
    classroomName: "",
    notes: "",
    selectedPdfMethod: "",
  }));
  const [configState, setConfigState] = useState<ClassroomConfigState>(defaultConfig);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState<number | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<"updated_at" | "created_at" | "label" | "students">("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const classrooms = useMemo<ClassroomDataset[]>(() => status?.classrooms ?? [], [status?.classrooms]);

  const enhancedEntries = useMemo(() => {
    const structured = (status?.structured_data as Record<string, unknown> | undefined) ?? {};
    const results = (structured.manipulation_results as Record<string, unknown> | undefined) ?? {};
    const enhanced = (results.enhanced_pdfs as Record<string, any> | undefined) ?? {};
    return Object.entries(enhanced)
      .filter(([, meta]) => meta && typeof meta === "object" && meta.status !== "error")
      .map(([method, meta]) => ({
        method,
        label: ENHANCEMENT_METHOD_LABELS[method] ?? method.replace(/_/g, " "),
        meta: meta ?? {},
      }));
  }, [status?.structured_data]);

  useEffect(() => {
    if (!formState.selectedPdfMethod && enhancedEntries.length) {
      setFormState((prev) => ({ ...prev, selectedPdfMethod: enhancedEntries[0].method }));
    }
  }, [enhancedEntries, formState.selectedPdfMethod]);

  const clampPercent = (value: number) => Math.min(100, Math.max(0, value));
  const toFraction = (value: number) => clampPercent(value) / 100;

  const handleConfigChange = useCallback((field: keyof ClassroomConfigState, value: number | boolean) => {
    setConfigState((prev) => ({
      ...prev,
      [field]: value,
    }));
  }, []);

  const handleResetForm = useCallback(() => {
    setFormState({ classroomName: "", notes: "", selectedPdfMethod: enhancedEntries[0]?.method ?? "" });
    setConfigState(defaultConfig);
    setFormError(null);
    setFormMessage(null);
  }, [enhancedEntries]);

  const handleSubmit = useCallback(async () => {
    if (!activeRunId) return;
    if (!formState.selectedPdfMethod) {
      setFormError("Select the attacked PDF variant used in the classroom.");
      setFormMessage(null);
      return;
    }

    setFormError(null);
    setFormMessage(null);
    setIsSubmitting(true);

    try {
      const cheatingRate = toFraction(configState.cheatingRatePercent);
      const llmRatio = toFraction(configState.llmSharePercent);
      const peerRatio = Math.max(0, 1 - llmRatio);
      const partialMin = toFraction(configState.partialCopyMinPercent);
      const partialMax = Math.max(partialMin, toFraction(configState.partialCopyMaxPercent));
      const fullCopyProbability = toFraction(configState.fullCopyProbabilityPercent);
      const paraphraseProbability = toFraction(configState.paraphraseProbabilityPercent);

      const payload: ClassroomCreationPayload = {
        classroom: {
          label: formState.classroomName.trim() || `Classroom ${classrooms.length + 1}`,
          notes: formState.notes.trim() || undefined,
          attacked_pdf_method: formState.selectedPdfMethod,
          origin: "generated",
        },
        config: {
          total_students: Math.max(1, Math.round(configState.totalStudents)),
          cheating_rate: cheatingRate,
          cheating_breakdown: {
            llm: llmRatio,
            peer: peerRatio,
          },
          copy_profile: {
            full_copy_probability: fullCopyProbability,
            partial_copy_min: partialMin,
            partial_copy_max: partialMax,
          },
          paraphrase_probability: paraphraseProbability,
          write_parquet: configState.writeParquet,
        },
      };

      const result = await createClassroomDataset(activeRunId, payload);
      if (result?.classroom_label) {
        setFormMessage(`Generated classroom dataset: ${result.classroom_label}`);
        setFormState((prev) => ({ ...prev, classroomName: "", notes: "" }));
      }
      setIsAdvancedOpen(false);
    } catch (err: any) {
      setFormError(err?.response?.data?.error || err?.message || "Failed to generate classroom dataset.");
      setFormMessage(null);
    } finally {
      setIsSubmitting(false);
    }
  }, [activeRunId, classrooms.length, configState, createClassroomDataset, formState]);

  const handleDelete = useCallback(
    async (classroomId: number) => {
      if (!activeRunId) return;
      setIsDeleting(classroomId);
      try {
        await deleteClassroomDataset(activeRunId, classroomId);
      } catch (err: any) {
        setFormError(err?.message || "Failed to delete classroom dataset.");
      } finally {
        setIsDeleting(null);
      }
    },
    [activeRunId, deleteClassroomDataset]
  );

  const handleEvaluate = useCallback(
    async (classroomId: number) => {
      if (!activeRunId) return;
      setIsEvaluating(classroomId);
      setFormError(null);
      try {
        await evaluateClassroom(activeRunId, classroomId);
      } catch (err: any) {
        setFormError(err?.message || "Failed to run classroom evaluation.");
      } finally {
        setIsEvaluating(null);
      }
    },
    [activeRunId, evaluateClassroom]
  );

  const filteredClassrooms = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const filtered = classrooms.filter((classroom) => {
      if (!normalizedQuery) return true;
      const haystacks = [
        classroom.classroom_label,
        classroom.classroom_key,
        classroom.notes,
        classroom.attacked_pdf_method,
      ]
        .filter(Boolean)
        .map((value) => String(value).toLowerCase());
      return haystacks.some((value) => value.includes(normalizedQuery));
    });

    const sorted = [...filtered].sort((a, b) => {
      const direction = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "label":
          return direction * String(a.classroom_label ?? "").localeCompare(String(b.classroom_label ?? ""));
        case "students":
          return direction * ((a.total_students ?? 0) - (b.total_students ?? 0));
        case "created_at":
        case "updated_at":
        default: {
          const aTime = a[sortKey] ? Date.parse(a[sortKey] as string) : 0;
          const bTime = b[sortKey] ? Date.parse(b[sortKey] as string) : 0;
          return direction * (aTime - bTime);
        }
      }
    });

    return sorted;
  }, [classrooms, query, sortDir, sortKey]);

  const completedCount = classrooms.filter((classroom) => classroom.evaluation?.status === "completed").length;

  return (
    <div className="panel classroom-manager" style={{ display: "grid", gap: "1.5rem" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
        <div>
          <h2 style={{ margin: 0 }}>🏫 Classroom Datasets</h2>
          <p style={{ margin: "0.35rem 0 0", color: "var(--muted)" }}>
            Generate synthetic student answer sheets or import classroom data before running cheating analytics.
          </p>
        </div>
        <div className="badge-stack">
          <span className="badge" title="Total datasets available">
            {classrooms.length} dataset{classrooms.length === 1 ? "" : "s"}
          </span>
          <span className="badge tag-muted" title="Evaluations completed">
            {completedCount} evaluation{completedCount === 1 ? "" : "s"}
          </span>
        </div>
      </header>

      <section className="classroom-grid">
        <article className="classroom-card classroom-card--form">
          <header>
            <div>
              <h3>Create dataset</h3>
              <p>Create a synthetic classroom dataset tied to a specific attacked PDF.</p>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => setIsAdvancedOpen((prev) => !prev)}
              title="Adjust simulation settings"
            >
              {isAdvancedOpen ? "Hide settings" : "Show settings"}
            </button>
          </header>

          <div className="classroom-form">
            <label className="form-field" title="Friendly name for this classroom dataset">
              <span className="form-label">Classroom name</span>
              <input
                type="text"
                value={formState.classroomName}
                placeholder="e.g., Algebra I – Period 3"
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, classroomName: event.target.value }))
                }
              />
            </label>

            <label className="form-field" title="Choose which attacked PDF variant powered this classroom">
              <span className="form-label">Attacked PDF variant *</span>
              <select
                value={formState.selectedPdfMethod}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, selectedPdfMethod: event.target.value }))
                }
              >
                <option value="">Select a variant</option>
                {enhancedEntries.map((entry) => (
                  <option key={entry.method} value={entry.method}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-field" title="Optional context about this classroom capture">
              <span className="form-label">Notes</span>
              <textarea
                rows={3}
                value={formState.notes}
                placeholder="Add context such as instructor, period, or assessment name"
                onChange={(event) => setFormState((prev) => ({ ...prev, notes: event.target.value }))}
              />
            </label>
          </div>

          {isAdvancedOpen ? (
            <div className="classroom-advanced">
              <h4>Simulation settings</h4>
              <div className="form-grid">
                <label className="form-field" title="Number of students to simulate">
                  <span className="form-label">Total students</span>
                  <input
                    type="number"
                    min={1}
                    value={configState.totalStudents}
                    onChange={(event) => handleConfigChange("totalStudents", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Percent of students who cheat">
                  <span className="form-label">Cheating rate (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.cheatingRatePercent}
                    onChange={(event) => handleConfigChange("cheatingRatePercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Share of cheaters using LLM assistance">
                  <span className="form-label">LLM share (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.llmSharePercent}
                    onChange={(event) => handleConfigChange("llmSharePercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Probability that a cheater copies the entire answer">
                  <span className="form-label">Full copy probability (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.fullCopyProbabilityPercent}
                    onChange={(event) => handleConfigChange("fullCopyProbabilityPercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Lower bound for partial copying">
                  <span className="form-label">Partial copy min (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.partialCopyMinPercent}
                    onChange={(event) => handleConfigChange("partialCopyMinPercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Upper bound for partial copying">
                  <span className="form-label">Partial copy max (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.partialCopyMaxPercent}
                    onChange={(event) => handleConfigChange("partialCopyMaxPercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field" title="Probability that a cheater paraphrases their answer">
                  <span className="form-label">Paraphrase probability (%)</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={configState.paraphraseProbabilityPercent}
                    onChange={(event) => handleConfigChange("paraphraseProbabilityPercent", Number(event.target.value))}
                  />
                </label>
                <label className="form-field">
                  <span className="form-label">Outputs</span>
                  <div className="toggle-field" title="Generate a Parquet file alongside JSON">
                    <input
                      type="checkbox"
                      checked={configState.writeParquet}
                      onChange={(event) => handleConfigChange("writeParquet", event.target.checked)}
                    />
                    <span>Include Parquet export</span>
                  </div>
                </label>
              </div>
            </div>
          ) : null}

          {formError ? <div className="panel-flash panel-flash--error">{formError}</div> : null}
          {formMessage ? <div className="panel-flash panel-flash--success">{formMessage}</div> : null}

          <div className="classroom-form__actions">
            <button type="button" className="primary-button" onClick={() => void handleSubmit()} disabled={isSubmitting}>
              {isSubmitting ? "Generating…" : "Generate dataset"}
            </button>
            <button type="button" className="ghost-button" onClick={handleResetForm} disabled={isSubmitting}>
              Reset
            </button>
          </div>
        </article>

        <article className="classroom-card classroom-card--list">
          <header className="classroom-list__header">
            <div>
              <h3>Classroom datasets</h3>
              <p>Search, sort, and manage existing datasets.</p>
            </div>
            <div className="classroom-list__controls">
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by name, variant, or notes"
              />
              <select value={`${sortKey}:${sortDir}`} onChange={(event) => {
                const [key, dir] = event.target.value.split(":");
                setSortKey(key as typeof sortKey);
                setSortDir(dir as typeof sortDir);
              }} title="Change sorting order">
                <option value="updated_at:desc">Updated ↓</option>
                <option value="updated_at:asc">Updated ↑</option>
                <option value="created_at:desc">Created ↓</option>
                <option value="created_at:asc">Created ↑</option>
                <option value="label:asc">Name A → Z</option>
                <option value="label:desc">Name Z → A</option>
                <option value="students:desc">Students ↓</option>
                <option value="students:asc">Students ↑</option>
              </select>
            </div>
          </header>

          <div className="table-wrapper">
            <table className="data-table classroom-table">
              <thead>
                <tr>
                  <th>Classroom</th>
                  <th>Variant</th>
                  <th title="Total simulated students">Students</th>
                  <th>Updated</th>
                  <th>Evaluation</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredClassrooms.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", padding: "1.25rem", color: "var(--muted)" }}>
                      {query ? "No classrooms match your search." : "No classroom datasets yet."}
                    </td>
                  </tr>
                ) : (
                  filteredClassrooms.map((classroom) => {
                    const label = classroom.classroom_label ?? classroom.classroom_key ?? `Classroom ${classroom.id}`;
                    const variantLabel = classroom.attacked_pdf_method
                      ? ENHANCEMENT_METHOD_LABELS[classroom.attacked_pdf_method] ?? classroom.attacked_pdf_method.replace(/_/g, " ")
                      : "Unknown";
                    const updatedAt = classroom.updated_at ? new Date(classroom.updated_at).toLocaleString() : "—";
                    const evaluationStatus = classroom.evaluation?.status ?? "pending";
                    const jsonPath = classroom.artifacts?.json;

                    return (
                      <tr
                        key={classroom.id}
                        className={selectedClassroomId === classroom.id ? "is-selected" : undefined}
                        onClick={() => setSelectedClassroomId(classroom.id)}
                      >
                        <td>
                          <div className="classroom-cell__label">
                            <span>{label}</span>
                            {classroom.notes ? (
                              <span className="classroom-cell__notes" title={classroom.notes}>
                                {classroom.notes}
                              </span>
                            ) : null}
                          </div>
                        </td>
                        <td>{variantLabel}</td>
                        <td>{classroom.total_students ?? "—"}</td>
                        <td>{updatedAt}</td>
                        <td>
                          {classroom.evaluation ? (
                            <span className={`status-tag status-${evaluationStatus}`}>
                              {evaluationStatus.replace(/_/g, " ")}
                            </span>
                          ) : (
                            <span className="status-tag status-pending">Pending</span>
                          )}
                        </td>
                        <td>
                          <div className="classroom-row-actions">
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelectedClassroomId(classroom.id);
                                setPreferredStage("classroom_dataset");
                              }}
                              title="View dataset details"
                            >
                              View
                            </button>
                            <button
                              type="button"
                              className="primary-button"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleEvaluate(classroom.id);
                              }}
                              disabled={isEvaluating === classroom.id}
                              title="Run cheating evaluation for this classroom"
                            >
                              {isEvaluating === classroom.id ? "Evaluating…" : "Evaluate"}
                            </button>
                            {jsonPath && activeRunId ? (
                              <a
                                className="ghost-button"
                                href={`/api/files/${activeRunId}/${jsonPath}`}
                                download
                                onClick={(event) => event.stopPropagation()}
                                title="Download dataset JSON"
                              >
                                Download
                              </a>
                            ) : null}
                            <button
                              type="button"
                              className="ghost-button danger"
                              onClick={(event) => {
                                event.stopPropagation();
                                void handleDelete(classroom.id);
                              }}
                              disabled={isDeleting === classroom.id}
                              title="Remove this classroom dataset"
                            >
                              {isDeleting === classroom.id ? "Removing…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </article>
      </section>

      <section className="panel-muted" style={{ display: "grid", gap: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Import student data (coming soon)</h3>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          Bring in answer sheets directly from LMS exports or proctoring tools. We will align each response to the
          selected attacked PDF to evaluate cheating risks per classroom.
        </p>
      </section>
    </div>
  );
};

export default ClassroomManagerPanel;
