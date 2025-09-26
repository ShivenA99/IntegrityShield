import { AttackType } from '../types';

interface UploadResponse {
  assessment_id: string;
  job_id?: string;
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

export async function bulkDeleteAssessments(ids: string[]): Promise<{ deleted: number }> {
  const resp = await fetch('/api/assessments/bulk-delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Delete failed (${resp.status}): ${txt}`);
  }
  return await resp.json();
}

export async function rerunAssessment(assessmentId: string, attackType: string, flags: Record<string, unknown> = {}): Promise<{ job_id: string }>{
  const resp = await fetch(`/api/assessments/${assessmentId}/rerun`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attack_type: attackType, flags }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Rerun failed (${resp.status}): ${txt}`);
  }
  return await resp.json();
}

export interface JobItem {
  id: string;
  assessment_id: string | null;
  new_assessment_id: string | null;
  action: string;
  params: any;
  status: 'queued'|'running'|'succeeded'|'failed'|'canceled';
  progress: number;
  message: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export async function getQueue(status?: string): Promise<{ items: JobItem[] }>{
  const usp = new URLSearchParams();
  if (status) usp.set('status', status);
  const resp = await fetch(`/api/assessments/queue?${usp.toString()}`);
  if (!resp.ok) throw new Error(`Queue failed (${resp.status})`);
  return await resp.json();
}

export async function getJob(jobId: string): Promise<JobItem> {
  const resp = await fetch(`/api/assessments/queue/${jobId}`);
  if (!resp.ok) throw new Error(`Job failed (${resp.status})`);
  return await resp.json();
}

export async function updateJob(jobId: string, action: 'requeue'|'cancel'|'move', order_index?: number): Promise<{ ok: boolean }>{
  const resp = await fetch(`/api/assessments/queue/${jobId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, order_index }),
  });
  if (!resp.ok) throw new Error(`Update job failed (${resp.status})`);
  return await resp.json();
}

export async function fetchOriginalFile(assessmentId: string): Promise<File> {
  const url = `/api/assessments/${assessmentId}/original`;
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
  const blob = await resp.blob();
  // Try to extract filename from header, fallback
  const disp = resp.headers.get('Content-Disposition') || '';
  const match = /filename="?([^";]+)"?/i.exec(disp);
  const name = match?.[1] || `original-${assessmentId}.pdf`;
  return new File([blob], name, { type: 'application/pdf' });
} 