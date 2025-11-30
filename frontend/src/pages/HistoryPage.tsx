import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@instructure/ui-buttons";
import { Table } from "@instructure/ui-table";
import { ScreenReaderContent } from "@instructure/ui-a11y-content";

import LTIShell from "@layout/LTIShell";
import { listRuns } from "@services/api/pipelineApi";

interface RunRow {
  run_id: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  mode?: string;
  artifacts?: number;
}

const PAGE_SIZE = 8;

const HistoryPage: React.FC = () => {
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
          setError(err?.message ?? "Unable to load runs.");
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
      const matchesSearch = search ? run.run_id.toLowerCase().includes(search.toLowerCase()) : true;
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

  const toggleSort = (field: "created_at" | "status") => {
    if (sortField === field) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  return (
    <LTIShell title="History" subtitle="Track previously shielded assessments and their outputs.">
      <div className="canvas-card">
        <div className="table-header">
          <div>
            <h2>Run history</h2>
            <p>{runs.length} total runs.</p>
          </div>
          <div className="table-controls">
            <input
              type="search"
              placeholder="Search run id"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(0);
              }}
            />
            <select
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value as typeof statusFilter);
                setPage(0);
              }}
            >
              <option value="all">All</option>
              <option value="completed">Completed</option>
              <option value="running">Running</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
        {error ? (
          <p className="form-error">{error}</p>
        ) : isLoading ? (
          <p>Loading runs…</p>
        ) : (
          <>
            <Table hover caption={<ScreenReaderContent>Run history</ScreenReaderContent>}>
              <Table.Head>
                <Table.Row>
                  <Table.ColHeader id="history-run">Run ID</Table.ColHeader>
                  <Table.ColHeader id="history-start">
                    <Button color="secondary" withBackground={false} size="small" onClick={() => toggleSort("created_at")}>
                      Started {sortField === "created_at" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                    </Button>
                  </Table.ColHeader>
                  <Table.ColHeader id="history-status">
                    <Button color="secondary" withBackground={false} size="small" onClick={() => toggleSort("status")}>
                      Status {sortField === "status" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                    </Button>
                  </Table.ColHeader>
                  <Table.ColHeader id="history-artifacts">Artifacts</Table.ColHeader>
                  <Table.ColHeader id="history-actions">Actions</Table.ColHeader>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {pagedRuns.map((run) => (
                  <Table.Row key={run.run_id}>
                    <Table.Cell>{run.run_id}</Table.Cell>
                    <Table.Cell>{run.created_at ? new Date(run.created_at).toLocaleString() : "—"}</Table.Cell>
                    <Table.Cell>
                      <span className={["status-pill", run.status === "completed" ? "completed" : run.status === "failed" ? "failed" : "running"].join(" ")}>
                        {run.status}
                      </span>
                    </Table.Cell>
                    <Table.Cell>{run.artifacts ?? "—"}</Table.Cell>
                    <Table.Cell>
                      <Button color="secondary" withBackground={false} onClick={() => window.open(`/dashboard?run=${run.run_id}`, "_blank")}>
                        View
                      </Button>
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
            <div className="pagination">
              <Button color="secondary" withBackground={false} interaction={page === 0 ? "disabled" : "enabled"} onClick={() => setPage((prev) => Math.max(0, prev - 1))}>
                Previous
              </Button>
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <Button
                color="secondary"
                withBackground={false}
                interaction={page + 1 >= totalPages ? "disabled" : "enabled"}
                onClick={() => setPage((prev) => Math.min(totalPages - 1, prev + 1))}
              >
                Next
              </Button>
            </div>
          </>
        )}
      </div>
    </LTIShell>
  );
};

export default HistoryPage;
