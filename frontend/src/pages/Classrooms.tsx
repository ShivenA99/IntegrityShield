import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import clsx from "clsx";

import { ENHANCEMENT_METHOD_LABELS } from "@constants/enhancementMethods";
import type {
  AnswerSheetGenerationConfig,
  AnswerSheetGenerationResult,
  ClassroomCreationPayload,
  ClassroomDataset,
  PipelineRunSummary,
} from "@services/types/pipeline";
import {
  createClassroomDataset,
  deleteClassroomDataset,
  evaluateClassroom,
  getClassroomEvaluation,
  getPipelineStatus,
  listRuns,
} from "@services/api/pipelineApi";

type ViewMode = "datasets" | "evaluations";

interface RunSummary {
  id: string;
  original_filename?: string | null;
  status?: string;
  created_at?: string;
  updated_at?: string;
}

interface EnhancedEntry {
  method: string;
  label: string;
  meta: Record<string, any>;
}

const defaultConfig = {
  totalStudents: 100,
  cheatingRatePercent: 35,
  llmSharePercent: 60,
  partialCopyMinPercent: 40,
  partialCopyMaxPercent: 75,
  fullCopyProbabilityPercent: 45,
  paraphraseProbabilityPercent: 65,
  writeParquet: false,
};

const ClassroomsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const viewParam = searchParams.get("view") === "evaluations" ? "evaluations" : "datasets";
  const [view, setView] = useState<ViewMode>(viewParam);

  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunStatus, setSelectedRunStatus] = useState<PipelineRunSummary | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [formState, setFormState] = useState({
    classroomName: "",
    notes: "",
    selectedPdfMethod: "",
  });
  const [configState, setConfigState] = useState(defaultConfig);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);

  const [isDeleting, setIsDeleting] = useState<number | null>(null);
  const [isEvaluating, setIsEvaluating] = useState<number | null>(null);
  const [evaluationPreview, setEvaluationPreview] = useState<Record<number, string>>({});
  const [datasetSearch, setDatasetSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortOption, setSortOption] = useState<"recent" | "name" | "students">("recent");

  const classrooms: ClassroomDataset[] = useMemo(
    () => selectedRunStatus?.classrooms ?? [],
    [selectedRunStatus?.classrooms]
  );
  const datasetStatusOptions = useMemo(() => {
    const statuses = new Set<string>();
    classrooms.forEach((classroom) => {
      if (classroom.status) {
        statuses.add(String(classroom.status));
      }
    });
    return Array.from(statuses).sort((a, b) => a.localeCompare(b));
  }, [classrooms]);
  const filteredClassrooms = useMemo(() => {
    let rows = [...classrooms];
    const query = datasetSearch.trim().toLowerCase();
    if (query) {
      rows = rows.filter((classroom) => {
        const label = classroom.classroom_label ?? classroom.classroom_key ?? "";
        const notes = classroom.notes ?? "";
        const method = classroom.attacked_pdf_method ?? "";
        return (
          label.toLowerCase().includes(query) ||
          notes.toLowerCase().includes(query) ||
          method.toLowerCase().includes(query)
        );
      });
    }
    if (statusFilter !== "all") {
      rows = rows.filter((classroom) => String(classroom.status ?? "").toLowerCase() === statusFilter.toLowerCase());
    }
    rows.sort((a, b) => {
      switch (sortOption) {
        case "name": {
          const aLabel = (a.classroom_label ?? a.classroom_key ?? "").toLowerCase();
          const bLabel = (b.classroom_label ?? b.classroom_key ?? "").toLowerCase();
          return aLabel.localeCompare(bLabel);
        }
        case "students":
          return (b.total_students ?? 0) - (a.total_students ?? 0);
        case "recent":
        default: {
          const aTime = a.updated_at ? new Date(a.updated_at).getTime() : 0;
          const bTime = b.updated_at ? new Date(b.updated_at).getTime() : 0;
          return bTime - aTime;
        }
      }
    });
    return rows;
  }, [classrooms, datasetSearch, sortOption, statusFilter]);

  const enhancedEntries: EnhancedEntry[] = useMemo(() => {
    const structured = (selectedRunStatus?.structured_data as Record<string, unknown> | undefined) ?? {};
    const manipulation = (structured.manipulation_results as Record<string, unknown> | undefined) ?? {};
    const enhanced: Record<string, any> = (manipulation.enhanced_pdfs as Record<string, any> | undefined) ?? {};
    return Object.entries(enhanced)
      .filter(([, meta]) => meta && typeof meta === "object" && meta.status !== "error")
      .map(([method, meta]) => ({
        method,
        label: ENHANCEMENT_METHOD_LABELS[method] ?? method.replace(/_/g, " "),
        meta: meta ?? {},
      }));
  }, [selectedRunStatus?.structured_data]);

  useEffect(() => {
    setRunsLoading(true);
    setRunsError(null);
    listRuns({ limit: 50, sortBy: "updated_at", sortDir: "desc" })
      .then(({ runs: runList }) => {
        const normalized = runList.map((run: any) => ({
          id: String(run.id ?? run.run_id ?? ""),
          original_filename: run.original_filename ?? run.filename ?? "",
          status: run.status,
          created_at: run.created_at,
          updated_at: run.updated_at,
        }));
        setRuns(normalized);
        if (!selectedRunId && normalized.length) {
          setSelectedRunId(normalized[0].id);
        }
      })
      .catch((err) => setRunsError(err?.message || "Failed to load runs."))
      .finally(() => setRunsLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshRunStatus = useCallback(
    async (runId: string) => {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const status = await getPipelineStatus(runId);
        setSelectedRunStatus(status);
        if (!formState.selectedPdfMethod) {
          const firstEntry = Object.entries(
            (status?.structured_data as any)?.manipulation_results?.enhanced_pdfs ?? {}
          )[0];
          if (firstEntry) {
            setFormState((prev) => ({ ...prev, selectedPdfMethod: firstEntry[0] }));
          }
        }
      } catch (err: any) {
        setStatusError(err?.response?.data?.error || err?.message || "Failed to load run details.");
        setSelectedRunStatus(null);
      } finally {
        setStatusLoading(false);
      }
    },
    [formState.selectedPdfMethod]
  );

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunStatus(null);
      return;
    }
    void refreshRunStatus(selectedRunId);
  }, [selectedRunId, refreshRunStatus]);

  useEffect(() => {
    if (view !== viewParam) {
      setSearchParams({ view });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);

  useEffect(() => {
    if (view !== viewParam) {
      setView(viewParam);
    }
  }, [view, viewParam]);

  const clampPercent = (value: number) => Math.min(100, Math.max(0, value));
  const toFraction = (value: number) => clampPercent(value) / 100;

  const handleConfigChange = useCallback((field: keyof typeof configState, value: number | boolean) => {
    setConfigState((prev) => ({
      ...prev,
      [field]: value,
    }));
  }, []);

  const handleResetForm = useCallback(() => {
    setFormState({
      classroomName: "",
      notes: "",
      selectedPdfMethod: enhancedEntries[0]?.method ?? "",
    });
    setConfigState(defaultConfig);
    setFormError(null);
    setFormMessage(null);
    setIsAdvancedOpen(false);
  }, [enhancedEntries]);

  const handleSubmit = useCallback(async () => {
    if (!selectedRunId) return;
    if (!formState.selectedPdfMethod) {
      setFormError("Select the attacked PDF variant used in the classroom.");
      setFormMessage(null);
      return;
    }

    setFormError(null);
    setFormMessage(null);
    setFormSubmitting(true);

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
        } satisfies AnswerSheetGenerationConfig,
      };

      const result: AnswerSheetGenerationResult = await createClassroomDataset(selectedRunId, payload);
      if (result?.classroom?.classroom_label) {
        setFormMessage(`Generated classroom dataset: ${result.classroom.classroom_label}`);
      }
      await refreshRunStatus(selectedRunId);
      setIsAdvancedOpen(false);
    } catch (err: any) {
      setFormError(err?.response?.data?.error || err?.message || "Failed to generate classroom dataset.");
      setFormMessage(null);
    } finally {
      setFormSubmitting(false);
    }
  }, [classrooms.length, configState, formState, refreshRunStatus, selectedRunId]);

  const handleDelete = useCallback(
    async (classroomId: number) => {
      if (!selectedRunId) return;
      setIsDeleting(classroomId);
      try {
        await deleteClassroomDataset(selectedRunId, classroomId);
        await refreshRunStatus(selectedRunId);
      } catch (err: any) {
        setFormError(err?.message || "Failed to delete classroom dataset.");
      } finally {
        setIsDeleting(null);
      }
    },
    [refreshRunStatus, selectedRunId]
  );

  const handleEvaluate = useCallback(
    async (classroomId: number) => {
      if (!selectedRunId) return;
      setIsEvaluating(classroomId);
      setFormError(null);
      try {
        await evaluateClassroom(selectedRunId, classroomId);
        await refreshRunStatus(selectedRunId);
        navigate(`/classrooms/${selectedRunId}/${classroomId}`);
      } catch (err: any) {
        setFormError(err?.message || "Failed to run classroom evaluation.");
      } finally {
        setIsEvaluating(null);
      }
    },
    [navigate, refreshRunStatus, selectedRunId]
  );

  const loadEvaluationPreview = useCallback(
    async (classroom: ClassroomDataset) => {
      if (!selectedRunId || !classroom.evaluation) {
        setEvaluationPreview((prev) => {
          const next = { ...prev };
          delete next[classroom.id];
          return next;
        });
        return;
      }
      try {
        const evaluation = await getClassroomEvaluation(selectedRunId, classroom.id);
        setEvaluationPreview((prev) => ({
          ...prev,
          [classroom.id]: evaluation?.completed_at ?? classroom.evaluation?.completed_at ?? "",
        }));
      } catch {
        // ignore preview errors
      }
    },
    [selectedRunId]
  );

  useEffect(() => {
    if (view === "evaluations") {
      classrooms.forEach((classroom) => {
        if (classroom.evaluation?.status === "completed") {
          void loadEvaluationPreview(classroom);
        }
      });
    }
  }, [classrooms, loadEvaluationPreview, view]);

  const selectedRun = runs.find((run) => run.id === selectedRunId);

  const datasetCountSummary = `${classrooms.length} dataset${classrooms.length === 1 ? "" : "s"}`;
  const completedEvaluations = classrooms.filter((c) => c.evaluation?.status === "completed").length;

  return (
    <div className="page classrooms-page">
      <header className="page-header">
        <div>
          <h1>Classrooms</h1>
          <p>Generate synthetic classrooms, import student datasets, and evaluate cheating behaviour.</p>
        </div>
        <div className="page-header__actions">
          <div className="badge-stack">
            <span className="badge">{datasetCountSummary}</span>
            <span className="badge tag-muted">
              {completedEvaluations} evaluation{completedEvaluations === 1 ? "" : "s"} complete
            </span>
          </div>
        </div>
      </header>

      <div className="card card--toolbar">
        <div className="card__section">
          <label className="form-field" title="Select the pipeline run to manage classroom datasets">
            <span className="form-label">Pipeline run</span>
            <select
              value={selectedRunId ?? ""}
              onChange={(event) => setSelectedRunId(event.target.value || null)}
              disabled={runsLoading}
            >
              {!runs.length ? <option value="">No runs available</option> : null}
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.original_filename ? `${run.original_filename} — ${run.id.slice(0, 6)}…` : run.id}
                </option>
              ))}
            </select>
          </label>
          <div className="toolbar-tabs">
            <button
              type="button"
              className={clsx("toolbar-tab", view === "datasets" && "is-active")}
              onClick={() => setView("datasets")}
            >
              Datasets
            </button>
            <button
              type="button"
              className={clsx("toolbar-tab", view === "evaluations" && "is-active")}
              onClick={() => setView("evaluations")}
            >
              Evaluations
            </button>
          </div>
        </div>
        {runsError ? <div className="panel-flash panel-flash--error">{runsError}</div> : null}
        {statusError ? <div className="panel-flash panel-flash--error">{statusError}</div> : null}
      </div>

      {view === "datasets" ? (
        <section className="panel classroom-manager">
          <header className="classroom-manager__summary">
            <div>
              <h2>Create classroom</h2>
              <p>
                Generate synthetic student answers for the selected run and attacked PDF. You can also import an
                existing dataset.
              </p>
            </div>
            <div className="badge-stack">
              <span className="badge">{datasetCountSummary}</span>
              <button type="button" className="ghost-button" onClick={handleResetForm}>
                Reset form
              </button>
            </div>
          </header>

          <div className="classroom-grid">
            <article className="classroom-card classroom-card--form">
              <header>
                <div>
                  <h3>Create classroom</h3>
                  <p>Create a synthetic dataset tied to a specific attacked PDF variant.</p>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => setIsAdvancedOpen((prev) => !prev)}
                    title="Adjust simulation settings"
                  >
                    {isAdvancedOpen ? "Hide settings" : "Show settings"}
                  </button>
                  <button type="button" className="ghost-button" title="Import dataset (coming soon)" disabled>
                    Import (coming soon)
                  </button>
                </div>
              </header>

              <div className="classroom-form">
                <label className="form-field" title="Friendly name for this classroom dataset">
                  <span className="form-label">Classroom name</span>
                  <input
                    type="text"
                    value={formState.classroomName}
                    placeholder="e.g., Algebra I – Period 3"
                    onChange={(event) => setFormState((prev) => ({ ...prev, classroomName: event.target.value }))}
                  />
                </label>

                <label className="form-field" title="Choose which attacked PDF variant powered this classroom">
                  <span className="form-label">Attacked PDF variant *</span>
                  <select
                    value={formState.selectedPdfMethod}
                    onChange={(event) => setFormState((prev) => ({ ...prev, selectedPdfMethod: event.target.value }))}
                    disabled={statusLoading || enhancedEntries.length === 0}
                  >
                    <option value="">Select a variant</option>
                    {enhancedEntries.map((entry) => {
                      const size = entry.meta.file_size_bytes ?? entry.meta.size_bytes;
                      const sizeLabel = size ? `${(size / 1024).toFixed(1)} KB` : "—";
                      return (
                        <option key={entry.method} value={entry.method}>
                          {entry.label} · {sizeLabel}
                        </option>
                      );
                    })}
                  </select>
                  {enhancedEntries.length === 0 ? (
                    <span className="form-helper">Render a PDF first to enable classroom generation.</span>
                  ) : null}
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
                      <span className="form-label">Cheating rate</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.cheatingRatePercent}
                        onChange={(event) => handleConfigChange("cheatingRatePercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="form-field" title="Percent of cheaters using LLM assistance">
                      <span className="form-label">LLM share</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.llmSharePercent}
                        onChange={(event) => handleConfigChange("llmSharePercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="form-field" title="Minimum copied content for partial-copy cheaters">
                      <span className="form-label">Partial copy min</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.partialCopyMinPercent}
                        onChange={(event) => handleConfigChange("partialCopyMinPercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="form-field" title="Maximum copied content for partial-copy cheaters">
                      <span className="form-label">Partial copy max</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.partialCopyMaxPercent}
                        onChange={(event) => handleConfigChange("partialCopyMaxPercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="form-field" title="Chance of full-copy cheaters duplicating the source">
                      <span className="form-label">Full copy probability</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.fullCopyProbabilityPercent}
                        onChange={(event) => handleConfigChange("fullCopyProbabilityPercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="form-field" title="Chance that cheaters paraphrase their answers">
                      <span className="form-label">Paraphrase probability</span>
                      <input
                        type="number"
                        min={0}
                        max={100}
                        value={configState.paraphraseProbabilityPercent}
                        onChange={(event) => handleConfigChange("paraphraseProbabilityPercent", Number(event.target.value))}
                      />
                    </label>
                    <label className="toggle-field" title="Write results to parquet (requires pandas)">
                      <input
                        type="checkbox"
                        checked={configState.writeParquet}
                        onChange={(event) => handleConfigChange("writeParquet", event.target.checked)}
                      />
                      <span>Write Parquet output</span>
                    </label>
                  </div>
                </div>
              ) : null}

              {formMessage ? <div className="panel-flash panel-flash--success">{formMessage}</div> : null}
              {formError ? <div className="panel-flash panel-flash--error">{formError}</div> : null}

              <footer className="classroom-card__footer">
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void handleSubmit()}
                  disabled={!selectedRunId || !enhancedEntries.length || formSubmitting}
                  aria-busy={formSubmitting}
                >
                  {formSubmitting ? "Generating…" : "Generate classroom"}
                </button>
              </footer>
            </article>

            <article className="classroom-card">
              <header>
                <div>
                  <h3>Classrooms</h3>
                  <p>All datasets for the selected run. Select a row to review or evaluate.</p>
                </div>
              </header>

              {statusLoading ? <p>Loading datasets…</p> : null}
              {!statusLoading && classrooms.length === 0 ? (
                <p style={{ color: "var(--muted)" }}>No classroom datasets yet.</p>
              ) : null}

              {classrooms.length ? (
                <>
                  <div className="classroom-table-toolbar">
                    <label className="toolbar-field" title="Search by classroom name, notes, or variant">
                      <span className="sr-only">Search classrooms</span>
                      <input
                        type="search"
                        value={datasetSearch}
                        onChange={(event) => setDatasetSearch(event.target.value)}
                        placeholder="Search classrooms"
                      />
                    </label>
                    <label className="toolbar-field" title="Filter by dataset generation status">
                      <span className="sr-only">Filter status</span>
                      <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                        <option value="all">All statuses</option>
                        {datasetStatusOptions.map((statusValue) => (
                          <option key={statusValue} value={statusValue.toLowerCase()}>
                            {statusValue.replace(/_/g, " ")}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="toolbar-field" title="Sort classroom list">
                      <span className="sr-only">Sort classrooms</span>
                      <select
                        value={sortOption}
                        onChange={(event) =>
                          setSortOption(event.target.value as "recent" | "name" | "students")
                        }
                      >
                        <option value="recent">Recent activity</option>
                        <option value="name">Name A–Z</option>
                        <option value="students">Students high → low</option>
                      </select>
                    </label>
                  </div>

                  {filteredClassrooms.length ? (
                    <div className="table-wrapper">
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Classroom</th>
                            <th>Variant</th>
                            <th>Students</th>
                            <th>Updated</th>
                            <th>Dataset</th>
                            <th>Evaluation</th>
                            <th>
                              <span className="sr-only">Actions</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredClassrooms.map((classroom) => {
                            const label = classroom.classroom_label ?? classroom.classroom_key ?? `Classroom ${classroom.id}`;
                            const variantLabel =
                              ENHANCEMENT_METHOD_LABELS[classroom.attacked_pdf_method ?? ""] ??
                              classroom.attacked_pdf_method?.replace(/_/g, " ") ??
                              "—";
                            const updatedAt = classroom.updated_at
                              ? new Date(classroom.updated_at).toLocaleString()
                              : "—";
                            const datasetStatus = (classroom.status ?? "pending").toLowerCase();
                            const evaluationStatus = (classroom.evaluation?.status ?? "pending").toLowerCase();
                            const jsonPath = classroom.artifacts?.json;

                            return (
                              <tr key={classroom.id}>
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
                                  <span className={`status-tag status-${datasetStatus}`}>
                                    {datasetStatus.replace(/_/g, " ")}
                                  </span>
                                </td>
                                <td>
                                  <span className={`status-tag status-${evaluationStatus}`}>
                                    {evaluationStatus.replace(/_/g, " ")}
                                  </span>
                                </td>
                                <td>
                                  <div className="classroom-row-actions">
                                    {jsonPath && selectedRunId ? (
                                      <a
                                        className="ghost-button"
                                        href={`/api/files/${selectedRunId}/${jsonPath}`}
                                        download
                                        title="Download dataset JSON"
                                      >
                                        Download
                                      </a>
                                    ) : null}
                                    <button
                                      type="button"
                                      className="ghost-button"
                                      onClick={() => navigate(`/classrooms/${selectedRunId}/${classroom.id}`)}
                                    >
                                      View
                                    </button>
                                    <button
                                      type="button"
                                      className="primary-button"
                                      onClick={() => void handleEvaluate(classroom.id)}
                                      disabled={isEvaluating === classroom.id}
                                      title="Run classroom evaluation"
                                    >
                                      {isEvaluating === classroom.id ? "Evaluating…" : "Evaluate"}
                                    </button>
                                    <button
                                      type="button"
                                      className="ghost-button"
                                      onClick={() => void handleDelete(classroom.id)}
                                      disabled={isDeleting === classroom.id}
                                      title="Delete classroom dataset"
                                    >
                                      Delete
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p style={{ color: "var(--muted)" }}>No classrooms match the current filters.</p>
                  )}
                </>
              ) : null}
            </article>
          </div>
        </section>
      ) : null}

      {view === "evaluations" ? (
        <section className="panel classroom-evaluations">
          <header className="panel-header panel-header--tight">
            <div>
              <h2>Evaluation overview</h2>
              <p>Track classroom evaluation status for the selected run. Open a dataset to view detailed metrics.</p>
            </div>
          </header>

          {classrooms.length === 0 ? (
            <p style={{ color: "var(--muted)" }}>
              No classrooms yet. Generate a dataset in the “Datasets” tab to start running evaluations.
            </p>
          ) : (
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Classroom</th>
                    <th>Status</th>
                    <th>Last evaluated</th>
                    <th>
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {classrooms.map((classroom) => {
                    const label = classroom.classroom_label ?? classroom.classroom_key ?? `Classroom ${classroom.id}`;
                    const evaluationStatus = classroom.evaluation?.status ?? "pending";
                    const preview = evaluationPreview[classroom.id];
                    return (
                      <tr key={classroom.id}>
                        <td>{label}</td>
                        <td>
                          <span className={`status-tag status-${evaluationStatus}`}>
                            {evaluationStatus.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td>{preview ? new Date(preview).toLocaleString() : "—"}</td>
                        <td>
                          <div className="classroom-row-actions">
                            <button
                              type="button"
                              className="primary-button"
                              onClick={() => navigate(`/classrooms/${selectedRunId}/${classroom.id}`)}
                            >
                              View evaluation
                            </button>
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={() => void handleEvaluate(classroom.id)}
                              disabled={isEvaluating === classroom.id}
                              title="Re-run evaluation"
                            >
                              {isEvaluating === classroom.id ? "Evaluating…" : "Re-run"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
};

export default ClassroomsPage;
