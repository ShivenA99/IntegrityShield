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