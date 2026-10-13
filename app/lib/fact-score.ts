export const FACT_SCORE_BANDS = ['verified', 'mostly_true', 'neutral', 'mostly_false', 'false'] as const;
export type FactScoreBand = typeof FACT_SCORE_BANDS[number];

export const FACT_SCORE_LABELS: Record<FactScoreBand, string> = {
  verified: '검증된 사실',
  mostly_true: '대체적으로 사실',
  neutral: '중립',
  mostly_false: '대체적으로 거짓',
  false: '거짓',
};

export function scoreBand(score: number): FactScoreBand {
  if (score >= 80) return 'verified';
  if (score >= 60) return 'mostly_true';
  if (score >= 40) return 'neutral';
  if (score >= 20) return 'mostly_false';
  return 'false';
}

export function scoreLabel(score: number): string {
  return FACT_SCORE_LABELS[scoreBand(score)];
}

export function normalizeFactScore(verdictCode: string, requestedScore: number): number {
  const score = Math.max(0, Math.min(100, Math.trunc(requestedScore)));
  if (verdictCode === 'mostly_supported') return Math.max(80, score);
  if (verdictCode === 'partially_supported') return Math.min(79, Math.max(60, score));
  if (verdictCode === 'contradicted') return Math.min(39, score);
  return 50;
}

type VerdictEntry = {
  id?: string; statement?: string; quote?: string; verdictCode?: string; verdict?: string | null;
  summary?: string; confirmed?: readonly string[]; evidenceIds?: readonly string[]; parts?: readonly VerdictEntry[];
};
export function verdictBreakdown(claims: readonly VerdictEntry[]) {
  const groups: Record<'confirmed'|'refuted'|'unresolved', {statement: string; summary?: string; confirmed: readonly string[]; claimId: string; evidenceIds: readonly string[]}[]> = {confirmed:[], refuted:[], unresolved:[]};
  for (const claim of claims) {
    for (const part of claim.parts?.length ? claim.parts : [claim]) {
      if (!part.verdictCode || part.verdictCode === 'not_checkable') continue;
      const key = part.verdictCode === 'mostly_supported' ? 'confirmed' : part.verdictCode === 'contradicted' ? 'refuted' : 'unresolved';
      groups[key].push({statement:part.statement || part.quote || '', summary:part.summary, confirmed:part.confirmed || [], claimId:claim.id || '', evidenceIds:part.evidenceIds || []});
    }
  }
  return groups;
}
