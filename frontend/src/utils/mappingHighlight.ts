import type { SubstringMapping } from "@services/types/questions";

export interface HighlightRange {
  start: number;
  end: number;
  mapping: SubstringMapping;
}

type Range = { start: number; end: number };

export function resolveHighlightRanges(
  text: string,
  mappings: SubstringMapping[]
): HighlightRange[] {
  if (!text) return [];

  const allocated: Range[] = [];
  const sorted = [...mappings].sort((a, b) => {
    const aPos = typeof a.start_pos === "number" ? a.start_pos : Number.MAX_SAFE_INTEGER;
    const bPos = typeof b.start_pos === "number" ? b.start_pos : Number.MAX_SAFE_INTEGER;
    return aPos - bPos;
  });

  const ranges: HighlightRange[] = [];

  sorted.forEach((mapping) => {
    const original = (mapping.original || "").trim();
    if (!original) return;

    const candidates = findCandidates(text, original, allocated);
    if (!candidates.length) return;

    const chosen = chooseCandidate(candidates, mapping, text.length);
    ranges.push({ start: chosen.start, end: chosen.end, mapping });
    allocated.push(chosen);
  });

  return ranges.sort((a, b) => a.start - b.start);
}

function findCandidates(text: string, needle: string, allocated: Range[]): Range[] {
  const candidates: Range[] = [];
  let index = text.indexOf(needle);

  while (index !== -1) {
    const candidate = { start: index, end: index + needle.length };
    if (!overlaps(candidate, allocated)) {
      candidates.push(candidate);
    }
    index = text.indexOf(needle, index + 1);
  }

  return candidates;
}

function chooseCandidate(candidates: Range[], mapping: SubstringMapping, textLength: number): Range {
  if (candidates.length === 1) {
    return candidates[0];
  }

  const latexRef = mapping.latex_stem_text || "";
  const latexLength = latexRef.length || 1;
  const startPos = typeof mapping.start_pos === "number" ? mapping.start_pos : 0;
  const predicted = Math.min(
    textLength,
    Math.max(0, Math.round((startPos / latexLength) * textLength))
  );

  return candidates.reduce((best, candidate) => {
    const bestDistance = Math.abs(best.start - predicted);
    const candidateDistance = Math.abs(candidate.start - predicted);
    if (candidateDistance < bestDistance) {
      return candidate;
    }
    if (candidateDistance === bestDistance && candidate.start < best.start) {
      return candidate;
    }
    return best;
  });
}

function overlaps(candidate: Range, allocated: Range[]): boolean {
  return allocated.some(
    (range) => Math.max(range.start, candidate.start) < Math.min(range.end, candidate.end)
  );
}





