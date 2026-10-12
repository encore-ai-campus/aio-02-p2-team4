import type { AnswerCitation, FactCheckAnswer, FactCheckResult, FactSource, FactClaim, FactEvidence } from '../lib/fact-check-contract';
// @ts-ignore -- explicit extension is required by the Node native test runner.
import { MODEL_OPTIONS } from '../lib/fact-check-contract.ts';
// @ts-ignore -- explicit extension is required by the Node native test runner.
import { safeSourceUrl } from './fact-check-client.ts';

type ReplyResult = Pick<FactCheckResult, 'answer' | 'sources' | 'evidence' | 'model' | 'claims'>;

export type AssistantReply = {
  answer: FactCheckAnswer;
  sources: FactSource[];
  meta: string;
  text?: string;
  judgments?: FactClaim[];
  evidence?: FactEvidence[];
  factScore?: number | null;
  verdict?: string | null;
  search?: string | null;
  scoreMode?: 'jev' | 'claims';
  scoreEngine?: string | null;
};

export function modelLabel(model: string | null): string {
  if (!model) return '모델 미확인';
  return MODEL_OPTIONS.find(option => option.id === model)?.label ?? model;
}

export function searchBackendLabel(sources: FactSource[]): string | null {
  const providers = new Set(sources.map(source => source.searchProvider));
  const tavily = providers.has('tavily_search');
  const llm = providers.has('openai_web_search') || providers.has('gemini_google_search');
  if (tavily && llm) return 'Tavily+LLM 검색';
  if (tavily) return 'Tavily 검색';
  if (llm) return 'LLM 검색';
  return null;
}

export type ResolvedAnswerCitation = {source: FactSource; href: string};
export type AnswerCitationDisplay = {
  citation: AnswerCitation;
  number: number;
  source: FactSource | null;
  href: string | null;
  linkTarget: 'external' | 'unavailable';
};

export type AnswerCitationDisplayState = {
  sourceNumbers: Map<string, number>;
  linkedSources: Set<string>;
};

export function createAnswerCitationDisplayState(sources: FactSource[] = []): AnswerCitationDisplayState {
  return {
    sourceNumbers: new Map(sources.map((source, index) => [source.id, index + 1])),
    linkedSources: new Set(),
  };
}

export function resolveAnswerCitationSource(citation: AnswerCitation, sources: FactSource[], verifiedEvidence = false): ResolvedAnswerCitation | null {
  const source = sources.find(item => item.id === citation.sourceId);
  if (!source || source.accessStatus !== 'verified' || (!verifiedEvidence && source.sourceType === '유튜브')) return null;
  const href = safeSourceUrl(source.url);
  return href ? {source, href} : null;
}

export function presentAnswerCitations(
  citations: AnswerCitation[],
  sources: FactSource[],
  state: AnswerCitationDisplayState,
  verifiedEvidence = false,
): AnswerCitationDisplay[] {
  const seenInBlock = new Set<string>();
  const displays: AnswerCitationDisplay[] = [];

  for (const citation of citations) {
    if (seenInBlock.has(citation.sourceId)) continue;
    seenInBlock.add(citation.sourceId);

    let number = state.sourceNumbers.get(citation.sourceId);
    if (number === undefined) {
      number = state.sourceNumbers.size + 1;
      state.sourceNumbers.set(citation.sourceId, number);
    }

    const resolved = resolveAnswerCitationSource(citation, sources, verifiedEvidence);
    if (!resolved) {
      displays.push({citation, number, source: null, href: null, linkTarget: 'unavailable'});
      continue;
    }
    if (state.linkedSources.has(citation.sourceId)) continue;
    state.linkedSources.add(citation.sourceId);

    displays.push({citation, number, source: resolved.source, href: resolved.href, linkTarget: 'external'});
  }

  return displays;
}

export function composeAssistantReply(result: ReplyResult, jevResult: ReplyResult | null = null): AssistantReply {
  const search = searchBackendLabel(result.sources);
  const meta = `${modelLabel(result.answer.model ?? result.model)}${search ? ` · ${search}` : ''} · ${result.sources.length}개 출처 · ${result.evidence.length}개 인용`;
  const reply: AssistantReply = {
    answer: result.answer,
    sources: result.sources,
    meta,
  };
  if (result.answer.status === 'judgment_only') {
    reply.judgments = result.claims;
    reply.evidence = result.evidence;
    reply.text = result.claims.map(claim => `${claim.verdict} · ${claim.summary}`).join('\n')
      || '검증 가능한 주장을 찾지 못했습니다. 확인할 원문·링크·이미지를 보내주세요.';
  }
  const claim = jevResult?.claims[0];
  if (claim) {
    reply.factScore = claim.factScore ?? null;
    reply.verdict = claim.verdict ?? null;
    reply.search = searchBackendLabel(jevResult?.sources ?? []);
    reply.scoreMode = 'jev';
    return reply;
  }
  const scored = result.claims.filter(item => item && Number.isInteger(item.factScore));
  if (scored.length) {
    const total = scored.reduce((sum, item) => sum + item.factScore, 0);
    reply.factScore = Math.round(total / scored.length);
    reply.verdict = scored.length === 1 ? (scored[0].verdict ?? null) : null;
    reply.scoreMode = 'claims';
    reply.scoreEngine = '종합';
  }
  return reply;
}
