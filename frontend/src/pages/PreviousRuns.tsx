import * as React from "react";
import { useMemo, useState, useCallback } from "react";

import { usePipeline } from "@hooks/usePipeline";
import * as pipelineApi from "@services/api/pipelineApi";
import { saveRecentRun } from "@services/utils/storage";
import { useNavigate } from "react-router-dom";

interface RunRow {
  run_id: string;
  filename: string;
  status: string;
  current_stage: string;
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
  const [sortBy, setSortBy] = useState<string>("created_at");
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

  const statusOptions = useMemo(() => ["pending", "running", "completed", "failed"], []);

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
    const newId = (result as any).run_id;
    setActiveRunId(newId);
    saveRecentRun(newId);
    await refreshStatus(newId);
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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', margin: 0 }}>
          <span role="img" aria-hidden="true">📚</span>
          Previous Runs
        </h2>
        <button className="pill-button" onClick={() => load()} title="Refresh run list">
          🔄 Refresh
        </button>
      </div>

      <div className="panel-card" style={{ display: 'grid', gap: 12 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <input
            placeholder="Search run id or filename"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ minWidth: 240 }}
          />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {statusOptions.map((s) => (
              <label key={s} className="tooltip" data-tip={`Filter by ${s}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <input
                  type="checkbox"
                  checked={status.includes(s)}
                  onChange={() => setStatus((prev) => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])}
                />
                <span>{s}</span>
              </label>
            ))}
          </div>
          <label className="tooltip" data-tip="Show soft deleted runs" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={includeDeleted} onChange={(e) => setIncludeDeleted(e.target.checked)} />
            Include deleted
          </label>
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
          <button className="pill-button" onClick={() => load()} title="Apply filters">
            🔎 Apply
          </button>
        </div>

        {isLoading && <div className="badge">Loading…</div>}
        {error && <div className="badge" style={{ background: 'rgba(248,113,113,0.2)', color: '#f87171' }}>{error}</div>}
      </div>

      <div className="panel-card" style={{ overflow: 'auto' }}>
        <table style={{ minWidth: 880 }}>
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
                <td style={{ fontFamily: 'monospace' }}>{r.run_id}</td>
                <td>{r.filename}</td>
                <td>
                  <span className="badge" style={{ background: 'rgba(56,189,248,0.18)', color: '#bae6fd' }}>{r.status}</span>
                </td>
                <td>{r.current_stage}</td>
                <td>{r.validated_count}/{r.total_questions}</td>
                <td>{r.created_at ? new Date(r.created_at).toLocaleString() : '-'}</td>
                <td>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      className="pill-button"
                      onClick={() => onView(r.run_id)}
                      title="Load this run on the dashboard"
                    >
                      👁️ View
                    </button>
                    <button
                      className="pill-button"
                      onClick={() => onDownloadStructured(r.run_id)}
                      title="Download structured data JSON"
                    >
                      📄 JSON
                    </button>
                    <button
                      className="pill-button"
                      onClick={() => onReRun(r.run_id)}
                      title="Launch a rerun with the same PDF"
                    >
                      🔁 Re-run
                    </button>
                    {!r.deleted && (
                      <button
                        className="pill-button"
                        onClick={() => onSoftDelete(r.run_id)}
                        title="Mark run as deleted without removing files"
                      >
                        💤 Soft delete
                      </button>
                    )}
                    <button
                      className="pill-button"
                      onClick={() => onDelete(r.run_id)}
                      title="Permanently delete this run"
                      style={{ background: 'rgba(239,68,68,0.25)', border: '1px solid rgba(239,68,68,0.4)', color: '#fecaca' }}
                    >
                      🗑️ Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {runs.length === 0 && !isLoading && (
              <tr>
                <td colSpan={7} style={{ textAlign: 'center', padding: 16, color: 'var(--muted)' }}>No runs found</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default PreviousRuns; 
