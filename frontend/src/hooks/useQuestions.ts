import { useEffect } from "react";
import useSWR from "swr";

import { fetchQuestions } from "@services/api/questionApi";
import type { QuestionListResponse } from "@services/types/questions";

export function useQuestions(runId: string | null) {
  const key = runId ? ["questions", runId] as const : null;

  const fetcher = (_key: readonly ["questions", string]) => fetchQuestions(_key[1]);
  const { data, error, isLoading, mutate } = useSWR<QuestionListResponse>(key, fetcher);

  useEffect(() => {
    if (!runId) {
      mutate(undefined, false);
    }
  }, [runId, mutate]);

  return {
    questions: data?.questions ?? [],
    total: data?.total ?? 0,
    isLoading,
    error,
    refresh: () => mutate(),
    mutate, // expose for optimistic updates
  };
}
