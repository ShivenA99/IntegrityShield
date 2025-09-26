import useSWR from "swr";

import { fetchQuestions } from "@services/api/questionApi";
import type { QuestionListResponse } from "@services/types/questions";

export function useQuestions(runId: string | null) {
  const key = runId ? ["questions", runId] : null;

  const { data, error, isLoading, mutate } = useSWR<QuestionListResponse>(key, ([, id]) => fetchQuestions(id));

  return {
    questions: data?.questions ?? [],
    total: data?.total ?? 0,
    isLoading,
    error,
    refresh: () => mutate(),
  };
}
