import * as React from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { PipelineRunSummary, PipelineStageName } from "@services/types/pipeline";
import { extractErrorMessage } from "@services/utils/errorHandling";
import { saveRecentRun, loadRecentRuns, removeRecentRun } from "@services/utils/storage";
import * as pipelineApi from "@services/api/pipelineApi";

interface PipelineContextValue {
  activeRunId: string | null;
  status: PipelineRunSummary | null;
  isLoading: boolean;
  error: string | null;
  setActiveRunId: (runId: string | null) => void;
  refreshStatus: (runId?: string, options?: { quiet?: boolean }) => Promise<void>;
  startPipeline: (payload: { file: File; config?: Partial<StartPipelineConfig> }) => Promise<string | null>;
  resumeFromStage: (runId: string, stage: PipelineStageName) => Promise<void>;
  deleteRun: (runId: string) => Promise<void>;
  resetActiveRun: (options?: { softDelete?: boolean }) => Promise<void>;
}

interface StartPipelineConfig {
  targetStages: PipelineStageName[];
  aiModels: string[];
  enhancementMethods: string[];
  skipIfExists: boolean;
  parallelProcessing: boolean;
}

const PipelineContext = createContext<PipelineContextValue | undefined>(undefined);

export const PipelineProvider: React.FC<{ children?: React.ReactNode }> = (props) => {
  const { children } = props;
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<PipelineRunSummary | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(
    async (runId?: string, options?: { quiet?: boolean }) => {
      const targetRunId = runId ?? activeRunId;
      if (!targetRunId) return;
      const quiet = options?.quiet ?? false;
      if (!quiet) {
        setIsLoading(true);
      }
      setError(null);
      try {
        const data = await pipelineApi.getPipelineStatus(targetRunId);
        setStatus(data);
        setActiveRunId(targetRunId);
        saveRecentRun(targetRunId);
      } catch (err) {
        setError(extractErrorMessage(err));
      } finally {
        if (!quiet) {
          setIsLoading(false);
        }
      }
    },
    [activeRunId]
  );

  const startPipeline = useCallback(
    async ({ file, config }: { file: File; config?: Partial<StartPipelineConfig> }) => {
      setIsLoading(true);
      setError(null);
      try {
        const formData = new FormData();
        formData.append("original_pdf", file);
        if (config?.targetStages) {
          config.targetStages.forEach((stage) => formData.append("target_stages", stage));
        }
        if (config?.aiModels) {
          config.aiModels.forEach((model) => formData.append("ai_models", model));
        }
        if (config?.enhancementMethods) {
          config.enhancementMethods.forEach((method) => formData.append("enhancement_methods", method));
        }
        if (config?.skipIfExists !== undefined) {
          formData.append("skip_if_exists", String(config.skipIfExists));
        }
        if (config?.parallelProcessing !== undefined) {
          formData.append("parallel_processing", String(config.parallelProcessing));
        }

        const { run_id } = await pipelineApi.startPipeline(formData);
        saveRecentRun(run_id);
        setActiveRunId(run_id);
        await refreshStatus(run_id);
        return run_id;
      } catch (err) {
        setError(extractErrorMessage(err));
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [refreshStatus]
  );

  const resumeFromStage = useCallback(async (runId: string, stage: PipelineStageName) => {
    try {
      await pipelineApi.resumePipeline(runId, stage);
      await refreshStatus(runId);
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, [refreshStatus]);

  const deleteRun = useCallback(async (runId: string) => {
    try {
      await pipelineApi.deletePipelineRun(runId);
      if (activeRunId === runId) {
        setActiveRunId(null);
        setStatus(null);
        removeRecentRun(runId);
      }
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }, [activeRunId]);

  const resetActiveRun = useCallback(async (options?: { softDelete?: boolean }) => {
    if (!activeRunId) return;

    try {
      if (options?.softDelete) {
        await pipelineApi.softDeleteRun(activeRunId).catch(() => undefined);
      }
    } catch (err) {
      console.warn("Failed to soft delete run", err);
    } finally {
      removeRecentRun(activeRunId);
      setActiveRunId(null);
      setStatus(null);
      setError(null);
    }
  }, [activeRunId]);

  // Bootstrap last active run from localStorage if none is set
  useEffect(() => {
    if (activeRunId) return;
    const recent = loadRecentRuns()[0];
    if (recent) {
      setActiveRunId(recent);
      void refreshStatus(recent, { quiet: true });
    }
  }, [activeRunId, refreshStatus]);

  useEffect(() => {
    if (!activeRunId) return;
    if (status?.status && ["completed", "failed"].includes(status.status)) return;

    const interval = window.setInterval(() => {
      refreshStatus(activeRunId, { quiet: true }).catch((error) => {
        console.warn("Failed to refresh pipeline status", error);
      });
    }, 4000);

    return () => {
      window.clearInterval(interval);
    };
  }, [activeRunId, status?.status, refreshStatus]);

  const value = useMemo(
    () => ({
      activeRunId,
      status,
      isLoading,
      error,
      setActiveRunId,
      refreshStatus,
      startPipeline,
      resumeFromStage,
      deleteRun,
      resetActiveRun,
    }),
    [
      activeRunId,
      status,
      isLoading,
      error,
      refreshStatus,
      startPipeline,
      resumeFromStage,
      deleteRun,
      resetActiveRun,
    ]
  );

  return <PipelineContext.Provider value={value}>{children}</PipelineContext.Provider>;
};

export function usePipelineContext(): PipelineContextValue {
  const ctx = useContext(PipelineContext);
  if (!ctx) {
    throw new Error("usePipelineContext must be used within a PipelineProvider");
  }
  return ctx;
}
