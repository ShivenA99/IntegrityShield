import { AttackType } from '../types';

interface UploadResponse {
  assessment_id: string;
}

interface EvaluationResponse {
  assessment_id: string;
  evaluation: {
    ai_answers: Record<number, string>;
    reference_answers: Record<number, string>;
    malicious_answers: Record<number, string>;
    evaluation: Record<number, {
      ai_answer: string;
      reference_answer: string;
      malicious_answer: string;
      chose_malicious: boolean;
      chose_correct: boolean;
      influenced: boolean;
      attack_successful: boolean;
    }>;
    success_rate: number;
  };
}

export interface AssessmentListItem {
  id: string;
  created_at: string;
  attack_type: string;
  status: string;
  original_filename: string | null;
  answers_filename: string | null;
  attacked_filename: string | null;
  report_filename: string | null;
  downloads: {
    original: string;
    attacked: string;
    report: string;
  };
}

export interface AssessmentListResponse {
  items: AssessmentListItem[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export async function uploadAssessment(
  originalPdf: File,
  answersPdf: File | null | undefined,
  attack: AttackType,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append('original_pdf', originalPdf);
  if (answersPdf) {
    form.append('answers_pdf', answersPdf);
  }
  form.append('attack_type', attack.toString());

  const resp = await fetch('/api/assessments/upload', {
    method: 'POST',
    body: form,
  });

  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Upload failed (${resp.status}): ${txt}`);
  }
  return (await resp.json()) as UploadResponse;
}

export async function evaluateAssessment(assessmentId: string): Promise<EvaluationResponse> {
  const resp = await fetch(`/api/assessments/${assessmentId}/evaluate`, {
    method: 'POST',
  });

  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Evaluation failed (${resp.status}): ${txt}`);
  }
  return (await resp.json()) as EvaluationResponse;
}

export async function listAssessments(params: Record<string, string | number | undefined> = {}): Promise<AssessmentListResponse> {
  const usp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) usp.set(k, String(v));
  });
  const url = `/api/assessments/?${usp.toString()}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`List failed (${resp.status}): ${txt}`);
  }
  return (await resp.json()) as AssessmentListResponse;
} 