import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@instructure/ui-buttons";
import { Text } from "@instructure/ui-text";

import LTIShell from "@layout/LTIShell";
import { PageSection } from "@components/layout/PageSection";
import { StatusPill } from "@components/shared/StatusPill";
import { listRuns } from "@services/api/pipelineApi";

interface RunRow {
  run_id: string;
  filename?: string;
  assessment_name?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  mode?: string;
  artifacts?: number;
}

const PAGE_SIZE = 12;

const HistoryPage: React.FC = () => {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<"created_at" | "status">("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "completed" | "running" | "failed">("all");

  useEffect(() => {
    let cancelled = false;
    const fetchRuns = async () => {
      setIsLoading(true);
      try {
        const response = await listRuns({ limit: 200, sortBy: "created_at", sortDir: "desc" });
        if (!cancelled) {
          setRuns(response.runs ?? []);
          setError(null);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message ?? "Unable to load assessments.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };
    fetchRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const matchesStatus = statusFilter === "all" || run.status === statusFilter;
      const matchesSearch = search
        ? (run.run_id.toLowerCase().includes(search.toLowerCase()) ||
           (run.assessment_name || "").toLowerCase().includes(search.toLowerCase()) ||
           (run.filename || "").toLowerCase().includes(search.toLowerCase()))
        : true;
      return matchesStatus && matchesSearch;
    });
  }, [runs, search, statusFilter]);

  const sortedRuns = useMemo(() => {
    return [...filteredRuns].sort((a, b) => {
      const aVal = (a as any)[sortField] ?? "";
      const bVal = (b as any)[sortField] ?? "";
      if (aVal === bVal) return 0;
      if (sortDir === "asc") {
        return aVal > bVal ? 1 : -1;
      }
      return aVal < bVal ? 1 : -1;
    });
  }, [filteredRuns, sortDir, sortField]);

  const pagedRuns = sortedRuns.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(sortedRuns.length / PAGE_SIZE));

  return (
    <LTIShell title="History">
      <PageSection title="Assessment History" subtitle={`${runs.length} total assessments`}>
        {/* Filters */}
        <div style={{
          display: 'flex',
          gap: '0.75rem',
          marginBottom: '1.5rem',
          flexWrap: 'wrap'
        }}>
          <input
            type="search"
            placeholder="Search by name, filename, or ID..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            style={{
              flex: 1,
              minWidth: '200px',
              padding: '0.5rem 0.75rem',
              border: '1px solid #e0e0e0',
              borderRadius: '0.375rem',
              fontSize: '0.875rem',
              fontFamily: 'inherit'
            }}
          />
          <div style={{
            display: 'inline-flex',
            backgroundColor: '#f5f5f5',
            borderRadius: '0.5rem',
            padding: '0.25rem',
            gap: '0.25rem'
          }}>
            {[
              { id: 'all', label: 'All' },
              { id: 'completed', label: 'Completed' },
              { id: 'running', label: 'Running' },
              { id: 'failed', label: 'Failed' }
            ].map((option) => (
              <button
                key={option.id}
                onClick={() => {
                  setStatusFilter(option.id as typeof statusFilter);
                  setPage(0);
                }}
                style={{
                  padding: '0.5rem 1rem',
                  border: 'none',
                  borderRadius: '0.375rem',
                  backgroundColor: statusFilter === option.id ? '#FF7F32' : 'transparent',
                  color: statusFilter === option.id ? '#ffffff' : '#666666',
                  fontWeight: statusFilter === option.id ? '600' : '400',
                  fontSize: '0.875rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  fontFamily: 'inherit'
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        {error ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <Text color="danger">{error}</Text>
          </div>
        ) : isLoading ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <Text color="secondary">Loading assessments…</Text>
          </div>
        ) : pagedRuns.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>
            <Text color="secondary" size="small">No assessments found</Text>
          </div>
        ) : (
          <>
            {/* Table Header */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '2fr 150px 120px 120px 180px',
              gap: '1rem',
              padding: '0.75rem 1rem',
              backgroundColor: '#f0f0f0',
              borderRadius: '0.375rem',
              marginBottom: '0.75rem',
              alignItems: 'center'
            }}>
              <Text size="x-small" weight="bold" transform="uppercase" style={{ color: '#666666', letterSpacing: '0.05em' }}>
                Assessment Name
              </Text>
              <Text size="x-small" weight="bold" transform="uppercase" style={{ color: '#666666', letterSpacing: '0.05em' }}>
                Created
              </Text>
              <Text size="x-small" weight="bold" transform="uppercase" style={{ color: '#666666', letterSpacing: '0.05em' }}>
                Status
              </Text>
              <Text size="x-small" weight="bold" transform="uppercase" style={{ color: '#666666', letterSpacing: '0.05em' }}>
                Files
              </Text>
              <Text size="x-small" weight="bold" transform="uppercase" style={{ color: '#666666', letterSpacing: '0.05em' }}>
                Actions
              </Text>
            </div>

            {/* Table Rows */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1.5rem' }}>
              {pagedRuns.map((run) => (
                <div
                  key={run.run_id}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '2fr 150px 120px 120px 180px',
                    gap: '1rem',
                    alignItems: 'center',
                    padding: '1rem',
                    backgroundColor: '#f9f9f9',
                    borderRadius: '0.5rem',
                    border: '1px solid #e0e0e0',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <Text weight="normal" size="small" style={{ color: '#333333' }}>
                      {run.assessment_name || run.filename || run.run_id}
                    </Text>
                    {run.assessment_name && run.filename && run.assessment_name !== run.filename && (
                      <div style={{ marginTop: '0.125rem' }}>
                        <Text color="secondary" size="x-small">
                          {run.filename}
                        </Text>
                      </div>
                    )}
                  </div>
                  <Text color="secondary" size="x-small">
                    {run.created_at ? new Date(run.created_at).toLocaleDateString() : "—"}
                  </Text>
                  <div>
                    <StatusPill status={run.status as any} />
                  </div>
                  <div>
                    {run.artifacts !== undefined && run.artifacts > 0 ? (
                      <span style={{
                        fontSize: '0.75rem',
                        color: '#666666',
                        backgroundColor: '#e0e0e0',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '0.25rem'
                      }}>
                        {run.artifacts} file{run.artifacts !== 1 ? 's' : ''}
                      </span>
                    ) : (
                      <Text color="secondary" size="x-small">—</Text>
                    )}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Button
                      color="secondary"
                      size="small"
                      withBackground={false}
                      onClick={() => navigate(`/dashboard?run=${run.run_id}&mode=readonly`)}
                    >
                      View
                    </Button>
                    <Button
                      color="secondary"
                      size="small"
                      withBackground={false}
                      onClick={() => navigate(`/files?run=${run.run_id}&mode=readonly`)}
                    >
                      Files
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '1rem',
              padding: '1rem',
              borderTop: '1px solid #e0e0e0'
            }}>
              <Button
                color="secondary"
                size="small"
                withBackground={false}
                interaction={page === 0 ? "disabled" : "enabled"}
                onClick={() => setPage((prev) => Math.max(0, prev - 1))}
              >
                Previous
              </Button>
              <Text size="small" color="secondary">
                Page {page + 1} of {totalPages}
              </Text>
              <Button
                color="secondary"
                size="small"
                withBackground={false}
                interaction={page + 1 >= totalPages ? "disabled" : "enabled"}
                onClick={() => setPage((prev) => Math.min(totalPages - 1, prev + 1))}
              >
                Next
              </Button>
            </div>
          </>
        )}
      </PageSection>
    </LTIShell>
  );
};

export default HistoryPage;
