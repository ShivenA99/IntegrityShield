import { AttackType } from '../types';

interface UploadResponse {
  assessment_id: string;
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
  form.append('attack_type', attack);

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