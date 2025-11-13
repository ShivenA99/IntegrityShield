import * as React from "react";
import { useMemo, useState, useCallback } from "react";

import { Eye, FileCode2, RefreshCcw, RotateCcw, Search, Trash2 } from "lucide-react";

import { usePipeline } from "@hooks/usePipeline";
import * as pipelineApi from "@services/api/pipelineApi";
import { saveRecentRun } from "@services/utils/storage";
import { useNavigate } from "react-router-dom";

interface RunRow {
  run_id: string;
  filename: string;
  status: string;
  current_stage: string;
  parent_run_id?: string | null;
  resume_target?: string | null;
  created_at?: string;
  updated_at?: string;
  completed_at?: string;
  deleted?: boolean;

  total_questions: number;
  validated_count: number;
}

const PreviousRuns: React.FC = () => {
  const { setActiveRunId, refreshStatus } = usePipeline();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<string[]>([]);
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const [sortBy, setSortBy] = useState<string>("updated_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await pipelineApi.listRuns({ q, status, includeDeleted, sortBy, sortDir, limit: 200, offset: 0 });
      setRuns(data.runs || []);
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setIsLoading(false);
    }
  }, [q, status, includeDeleted, sortBy, sortDir]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const statusOptions = useMemo(() => ["pending", "running", "paused", "completed", "failed"], []);

  const toggleStatus = useCallback((value: string) => {
    setStatus((prev) => (prev.includes(value) ? prev.filter((item) => item !== value) : [...prev, value]));
  }, [setStatus]);

  const onSoftDelete = async (runId: string) => {
    await pipelineApi.softDeleteRun(runId);
    await load();
  };

  const onDelete = async (runId: string) => {
    await pipelineApi.deletePipelineRun(runId);
    await load();
  };

  const onView = async (runId: string) => {
    setActiveRunId(runId);
    saveRecentRun(runId);
    await refreshStatus(runId);
    navigate("/dashboard");
  };

  const onReRun = async (runId: string) => {
    const result = await pipelineApi.rerunRun({ source_run_id: runId });
    const newId = result.run_id;
    setActiveRunId(newId);
    saveRecentRun(newId);
    await new Promise((resolve) => setTimeout(resolve, 300));
    await refreshStatus(newId, { retries: 5, retryDelayMs: 400 });
    await load();
    navigate("/dashboard");
  };

  const onDownloadStructured = async (runId: string) => {
    // Fallback: download structured JSON from status endpoint
    const data = await pipelineApi.getPipelineStatus(runId);
    const blob = new Blob([JSON.stringify(data.structured_data || {}, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${runId}_structured.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page previous-runs">
      <header className="page-header">
        <div className="page-header__title">
          <h1>Previous Runs</h1>
          <p>Review history, rerun stages, and investigate artifacts.</p>
        </div>
        <div className="page-header__actions">
          <button type="button" className="icon-button" onClick={load} title="Refresh run list">
            <RefreshCcw size={17} aria-hidden="true" />
          </button>
        </div>
      </header>

      <section className="panel filters-panel">
        <div className="filters-grid">
          <label className="input-with-icon">
            <Search size={16} aria-hidden="true" />
            <input
              placeholder="Search run id or filename"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="filters-grid__chips">
            {statusOptions.map((s) => {
              const active = status.includes(s);
              return (
                <button
                  key={s}
                  type="button"
                  className={`filter-chip ${active ? "is-active" : ""}`}
                  onClick={() => toggleStatus(s)}
                >
                  {s}
                </button>
              );
            })}
          </div>
          <label className="filters-checkbox">
            <input type="checkbox" checked={includeDeleted} onChange={(e) => setIncludeDeleted(e.target.checked)} />
            <span>Include deleted</span>
          </label>
          <div className="filters-selects">
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
              <option value="created_at">Sort: Created</option>
              <option value="updated_at">Sort: Updated</option>
              <option value="status">Sort: Status</option>
              <option value="filename">Sort: Filename</option>
              <option value="validated_ratio">Sort: Validated %</option>
            </select>
            <select value={sortDir} onChange={(e) => setSortDir(e.target.value as any)}>
              <option value="desc">Desc</option>
              <option value="asc">Asc</option>
            </select>
          </div>
        </div>
        {error ? <div className="panel-flash panel-flash--error">{error}</div> : null}
      </section>

      <section className="panel runs-table-panel">
        {isLoading ? (
          <div className="panel-loading">
            <div className="panel-loading__indicator" aria-hidden="true" />
            <span>Loading runs…</span>
          </div>
        ) : (
          <div className="table-scroll">
            <table className="runs-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Filename</th>
                  <th>Status</th>
                  <th>Stage</th>
                  <th>Validated</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id}>
                    <td className="mono-cell">{r.run_id}</td>
                    <td>{r.filename || "—"}</td>
                    <td>
                      <span className={`status-tag status-${r.status}`}>{r.status}</span>
                    </td>
                    <td>{r.current_stage ? r.current_stage.replace(/_/g, " ") : "—"}</td>
                    <td>
                      {r.validated_count}/{r.total_questions}
                    </td>
                    <td>{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                    <td>
                      <div className="runs-actions">
                        <button
                          type="button"
                          className="ghost-button button-with-icon"
                          onClick={() => onView(r.run_id)}
                          title="Load this run on the dashboard"
                        >
                          <Eye size={15} aria-hidden="true" />
                          <span>View</span>
                        </button>
                        <button
                          type="button"
                          className="ghost-button button-with-icon"
                          onClick={() => onDownloadStructured(r.run_id)}
                          title="Download structured data JSON"
                        >
                          <FileCode2 size={15} aria-hidden="true" />
                          <span>JSON</span>
                        </button>
                        <button
                          type="button"
                          className="ghost-button button-with-icon"
                          onClick={() => onReRun(r.run_id)}
                          title="Create a new run from this source"
                        >
                          <RotateCcw size={15} aria-hidden="true" />
                          <span>Re-run</span>
                        </button>
                        {!r.deleted && (
                          <button
                            type="button"
                            className="ghost-button button-with-icon danger"
                            onClick={() => onSoftDelete(r.run_id)}
                            title="Mark run as deleted"
                          >
                            <Trash2 size={15} aria-hidden="true" />
                            <span>Delete</span>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-cell">
                      No runs found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default PreviousRuns; 
