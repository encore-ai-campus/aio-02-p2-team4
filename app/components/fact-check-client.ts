import type { AgentEvent, AnswerBlock, FactCheckAnswer, FactCheckResult, FactClaim, FactSource, MarketContext, ProgressClaim, ProgressSource } from '../lib/fact-check-contract';
// @ts-ignore -- explicit extension is required by the Node 24 native test runner.
import { FACT_SCORE_BANDS, scoreBand, scoreLabel } from '../lib/fact-score.ts';
// @ts-ignore -- explicit extension is required by the Node native test runner.
import { VERDICTS } from '../lib/fact-check-contract.ts';

type Options = {
  signal?: AbortSignal;
  onStage?: (event: Extract<AgentEvent, {type: 'stage'}>) => void;
  onSources?: (event: Extract<AgentEvent, {type: 'sources'}>) => void;
  onPreview?: (event: Extract<AgentEvent, {type: 'preview'}>) => void;
};
export class FactCheckError extends Error {
  code: string;
  constructor(code: string, message: string) {super(message); this.name = 'FactCheckError'; this.code = code;}
}
export function safeSourceUrl(value: string): string | null {
  try {const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null;} catch {return null;}
}
export function faviconUrlFor(value: string): string | null {
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname) return null;
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(url.hostname)}&sz=64`;
  } catch {return null;}
}
function validSourceMetadata(source: FactSource): boolean {
  return (source.searchProvider == null || ['openai_web_search', 'gemini_google_search', 'tavily_search'].includes(source.searchProvider))
    && (source.searchQuery == null || (typeof source.searchQuery === 'string' && source.searchQuery.length <= 300))
    && (source.candidateOrder == null || (Number.isInteger(source.candidateOrder) && source.candidateOrder >= 1 && source.candidateOrder <= 1000 && source.searchProvider != null));
}
function validAnswer(value: unknown, sources: FactSource[]): value is FactCheckAnswer {
  if (!value || typeof value !== 'object') return false;
  const answer = value as FactCheckAnswer;
  if (!['grounded','partial','insufficient_evidence','synthesis_failed','judgment_only'].includes(answer.status) || !Array.isArray(answer.sections) || answer.sections.length > 4
      || !(answer.model === null || (typeof answer.model === 'string' && answer.model.length <= 100))
      || !(answer.reasoning === null || answer.reasoning === 'max' || answer.reasoning === 'high')) return false;
  if (answer.status === 'judgment_only') return answer.overview === null && answer.conclusion === null && answer.sections.length === 0 && answer.model === null && answer.reasoning === null;
  const validBlock = (value: unknown, citationsRequired: boolean): value is AnswerBlock => {
    if (!value || typeof value !== 'object') return false;
    const block = value as AnswerBlock;
    return typeof block.text === 'string' && block.text.length >= 1 && block.text.length <= 1200
      && Array.isArray(block.citations) && block.citations.length <= 3 && (!citationsRequired || block.citations.length > 0)
      && block.citations.every(citation => citation && typeof citation.sourceId === 'string' && citation.sourceId.length >= 1 && citation.sourceId.length <= 100
        && typeof citation.quote === 'string' && citation.quote.length >= 1 && citation.quote.length <= 2000
        && sources.some(source => source.id === citation.sourceId && source.accessStatus === 'verified' && source.sourceType !== '유튜브'));
  };
  const citationsRequired = answer.status === 'grounded' || answer.status === 'partial';
  if (answer.overview !== null && !validBlock(answer.overview, citationsRequired)) return false;
  if (answer.conclusion !== null && !validBlock(answer.conclusion, citationsRequired)) return false;
  if (citationsRequired && (answer.overview === null || answer.conclusion === null)) return false;
  if (!citationsRequired && answer.sections.length > 0) return false;
  return answer.sections.every(section => section && typeof section === 'object'
    && ['supporting','counter','uncertainty','context'].includes(section.kind)
    && typeof section.title === 'string' && section.title.length >= 1 && section.title.length <= 120
    && Array.isArray(section.items) && section.items.length >= 1 && section.items.length <= 3
    && section.items.every(item => validBlock(item, citationsRequired)));
}
function validYoutubeMetadata(source: FactSource): boolean {
  // Optional keys may be absent when an older backend serves the stream; treat missing as null.
  const publishedAt = source.youtubePublishedAt;
  const validDate = publishedAt == null || (typeof publishedAt === 'string' && publishedAt.length <= 50
    && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(publishedAt)
    && Number.isFinite(Date.parse(publishedAt)));
  return (source.youtubeChannelTitle == null || (typeof source.youtubeChannelTitle === 'string' && source.youtubeChannelTitle.length <= 300))
    && validDate
    && (source.youtubeViewCount == null || (typeof source.youtubeViewCount === 'string' && /^\d{1,30}$/.test(source.youtubeViewCount)))
    && (source.sourceType === '유튜브' || (source.youtubeChannelTitle == null && source.youtubePublishedAt == null && source.youtubeViewCount == null));
}
function validEvidenceSection(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const evidence = value as Record<string, unknown>;
  const title = evidence.sectionTitle;
  const text = evidence.sectionText;
  const truncated = evidence.sectionTruncated;
  const hasTitle = typeof title === 'string';
  const hasText = typeof text === 'string';
  return (title == null || (hasTitle && title.length >= 1 && title.length <= 300))
    && (text == null || (hasText && text.length >= 1 && text.length <= 8000))
    && (truncated === undefined || typeof truncated === 'boolean')
    && hasTitle === hasText
    && (truncated !== true || hasText);
}
function validMarket(value: unknown): value is MarketContext {
  if (value == null) return true;
  if (typeof value !== 'object') return false;
  const market = value as MarketContext;
  const numberOrNull = (n: unknown) => n == null || (typeof n === 'number' && Number.isFinite(n));
  return (market.source === 'finnhub' || market.source === 'krx')
    && typeof market.symbol === 'string' && market.symbol.length >= 1 && market.symbol.length <= 16
    && (market.displayName == null || (typeof market.displayName === 'string' && market.displayName.length <= 100))
    && numberOrNull(market.current) && numberOrNull(market.previousClose) && numberOrNull(market.changePercent)
    && (market.dataAsOf == null || typeof market.dataAsOf === 'string')
    && Array.isArray(market.candles) && market.candles.length <= 90
    && market.candles.every(candle => candle && typeof candle.time === 'number' && Number.isFinite(candle.time) && candle.time >= 0
      && [candle.open, candle.high, candle.low, candle.close].every(n => typeof n === 'number' && Number.isFinite(n))
      && (candle.volume == null || (typeof candle.volume === 'number' && Number.isFinite(candle.volume))));
}
function validClaimParts(claim: FactClaim, result: FactCheckResult): boolean {
  if (claim.refuted !== undefined && (!Array.isArray(claim.refuted) || claim.refuted.length > 5 || !claim.refuted.every(text => typeof text === 'string'))) return false;
  if (claim.parts === undefined) return true;
  if (!Array.isArray(claim.parts) || claim.parts.length === 1 || claim.parts.length > 3) return false;
  const linked: string[] = [];
  for (const part of claim.parts) {
    if (!part || typeof part.statement !== 'string' || part.statement.length < 1 || part.statement.length > 2000
        || !VERDICTS.includes(part.verdictCode) || typeof part.verdict !== 'string' || part.verdict.length < 1 || part.verdict.length > 100
        || typeof part.summary !== 'string' || part.summary.length < 1 || part.summary.length > 2000
        || (part.confirmed !== undefined && (!Array.isArray(part.confirmed) || part.confirmed.length > 5 || !part.confirmed.every(text => typeof text === 'string' && text.length <= 2000)))
        || !Number.isInteger(part.factScore) || part.factScore < 0 || part.factScore > 100
        || !Array.isArray(part.evidenceIds) || part.evidenceIds.length > 2) return false;
    const quotes = part.evidenceIds.map(id => result.evidence.find(item => item.id === id && item.claimId === claim.id && item.quoteVerified));
    if (part.evidenceIds.some(id => !claim.evidenceIds.includes(id)) || quotes.some(item => !item)) return false;
    const relations = new Set(quotes.map(item => item?.relation));
    if (part.verdictCode === 'mostly_supported' && (!relations.has('supports') || relations.has('contradicts'))) return false;
    if (part.verdictCode === 'contradicted' && (!relations.has('contradicts') || relations.has('supports'))) return false;
    linked.push(...part.evidenceIds);
  }
  return !claim.parts.length || (new Set(linked).size === linked.length && linked.length === claim.evidenceIds.length);
}

export function validResult(value: unknown): value is FactCheckResult {
  if (!value || typeof value !== 'object') return false;
  const r = value as FactCheckResult;
  return r.demo === false && typeof r.text === 'string' && typeof r.focus === 'string' && typeof r.checkedAt === 'string' && typeof r.model === 'string' && (r.reasoning === 'max' || r.reasoning === 'high')
    && Array.isArray(r.claims) && r.claims.length <= 3 && r.claims.every(c => typeof c.id === 'string' && typeof c.quote === 'string' && (c.statement === undefined || typeof c.statement === 'string' && c.statement.length <= 12000) && Number.isInteger(c.start) && Number.isInteger(c.end) && c.start >= 0 && c.end > c.start && r.text.slice(c.start, c.end) === c.quote && Number.isInteger(c.factScore) && c.factScore >= 0 && c.factScore <= 100 && FACT_SCORE_BANDS.includes(c.scoreBand) && c.scoreBand === scoreBand(c.factScore) && c.scoreLabel === scoreLabel(c.factScore) && typeof c.summary === 'string' && typeof c.tone === 'string' && typeof c.verdict === 'string' && [c.confirmed,c.unresolved,c.warnings,c.evidenceIds].every(a=>Array.isArray(a)&&a.every(s=>typeof s==='string')))
    && Array.isArray(r.sources) && r.sources.every(s => ['id','url','title','publisher','retrievedAt','sourceType'].every(k=>typeof s[k as keyof typeof s]==='string') && ['verified','unavailable'].includes(s.accessStatus) && (s.publishedAt == null || typeof s.publishedAt === 'string') && (s.originGroupId == null || typeof s.originGroupId === 'string') && (s.youtubeTitle == null || (typeof s.youtubeTitle === 'string' && s.youtubeTitle.length <= 300)) && Array.isArray(s.youtubeComments) && s.youtubeComments.length <= 10 && s.youtubeComments.every(comment => typeof comment === 'string' && comment.length <= 10000) && ['not_applicable','not_configured','collected','unavailable'].includes(s.youtubeDataStatus) && (s.sourceType === '유튜브' ? s.youtubeDataStatus !== 'not_applicable' : s.youtubeDataStatus === 'not_applicable'))
    && r.sources.every(validSourceMetadata)
    && r.sources.every(validYoutubeMetadata)
    && Array.isArray(r.evidence) && r.evidence.every(e=>['id','claimId','sourceId','quote'].every(k=>typeof e[k as keyof typeof e]==='string') && (e.quoteTranslation === undefined || e.quoteTranslation === null || typeof e.quoteTranslation === 'string') && typeof e.quoteVerified === 'boolean' && validEvidenceSection(e))
    && Array.isArray(r.warnings) && r.warnings.every(w=>typeof w==='string') && validAnswer(r.answer,r.sources)
    && validMarket((r as Record<string, unknown>).market)
    && r.claims.every(claim => validClaimParts(claim, r));
}
function validProgressSource(value: unknown): value is ProgressSource {
  if (!value || typeof value !== 'object') return false;
  const source = value as Record<string, unknown>;
  return typeof source.id === 'string' && source.id.length >= 1 && source.id.length <= 100
    && typeof source.url === 'string' && source.url.length <= 2048 && safeSourceUrl(source.url) !== null
    && typeof source.title === 'string' && source.title.length >= 1 && source.title.length <= 300
    && typeof source.publisher === 'string' && source.publisher.length >= 1 && source.publisher.length <= 300
    && ['candidate','verified','unavailable'].includes(String(source.accessStatus))
    && typeof source.sourceType === 'string' && source.sourceType.length >= 1 && source.sourceType.length <= 100;
}
function validProgressSources(value: unknown): value is ProgressSource[] {
  if (!Array.isArray(value) || value.length > 6) return false;
  const ids = new Set<string>();
  return (value as unknown[]).every(item => {
    if (!validProgressSource(item) || ids.has(item.id)) return false;
    ids.add(item.id);
    return true;
  });
}
function validProgressCitation(value: unknown, sources: ProgressSource[]): boolean {
  if (!value || typeof value !== 'object') return false;
  const citation = value as Record<string, unknown>;
  return typeof citation.sourceId === 'string' && citation.sourceId.length >= 1 && citation.sourceId.length <= 100
    && typeof citation.quote === 'string' && citation.quote.length >= 1 && citation.quote.length <= 2000
    && sources.some(source => source.id === citation.sourceId && source.accessStatus === 'verified' && source.sourceType !== '유튜브');
}
function validProgressClaim(value: unknown, sources: ProgressSource[]): value is ProgressClaim {
  if (!value || typeof value !== 'object') return false;
  const claim = value as Record<string, unknown>;
  return typeof claim.id === 'string' && claim.id.length >= 1 && claim.id.length <= 100
    && typeof claim.quote === 'string' && claim.quote.length >= 1 && claim.quote.length <= 12000
    && typeof claim.summary === 'string' && claim.summary.length >= 1 && claim.summary.length <= 2000
    && typeof claim.verdict === 'string' && claim.verdict.length >= 1 && claim.verdict.length <= 100
    && Array.isArray(claim.citations) && claim.citations.length <= 3
    && (claim.citations as unknown[]).every(citation => validProgressCitation(citation, sources));
}
function validProgressClaims(value: unknown, sources: ProgressSource[]): value is ProgressClaim[] {
  if (!Array.isArray(value) || value.length > 3) return false;
  const ids = new Set<string>();
  return (value as unknown[]).every(item => {
    if (!validProgressClaim(item, sources) || ids.has(item.id)) return false;
    ids.add(item.id);
    return true;
  });
}
export async function readFactCheckStream(response: Response, options: Options = {}): Promise<FactCheckResult> {
  options.signal?.throwIfAborted();
  if (!response.ok) {
    const error = await response.json().catch(()=>null);
    throw new FactCheckError(typeof error?.code === 'string' ? error.code : 'HTTP_ERROR', typeof error?.message === 'string' ? error.message : `서버 요청에 실패했습니다 (${response.status}).`);
  }
  if (!response.headers.get('content-type')?.includes('application/x-ndjson') || !response.body) throw new FactCheckError('PROTOCOL', '검증 응답 형식이 올바르지 않습니다.');
  const reader = response.body.getReader();
  const abort = () => {void reader.cancel().catch(()=>{});};
  options.signal?.addEventListener('abort', abort, {once:true});
  const decoder = new TextDecoder();
  let buffer = '';
  let result: FactCheckResult | undefined;
  let progressSources: ProgressSource[] = [];
  function line(value: string) {
    if (!value.trim()) return;
    let event: AgentEvent;
    try {event = JSON.parse(value);} catch {throw new FactCheckError('PROTOCOL', '검증 스트림을 읽을 수 없습니다.');}
    if (!event || !['stage','sources','preview','result','error'].includes(event.type)) throw new FactCheckError('PROTOCOL', '알 수 없는 스트림 이벤트입니다.');
    if (event.type === 'error') throw new FactCheckError(event.code, event.message || '검증 요청에 실패했습니다.');
    if (event.type === 'stage') {
      if (!['extracting','searching','reading','verifying','synthesizing'].includes(event.stage) || typeof event.message !== 'string') throw new FactCheckError('PROTOCOL','잘못된 스트림 단계입니다.');
      options.onStage?.(event);
    }
    if (event.type === 'sources') {
      if (!['found','read'].includes(event.phase) || !validProgressSources(event.sources)) throw new FactCheckError('PROTOCOL','잘못된 진행 출처입니다.');
      progressSources = event.sources;
      options.onSources?.(event);
    }
    if (event.type === 'preview') {
      if (!validProgressClaims(event.claims, progressSources)) throw new FactCheckError('PROTOCOL','진행 요약의 출처 연결이 올바르지 않습니다.');
      options.onPreview?.(event);
    }
    if (event.type === 'result') {if (!validResult(event.result)) throw new FactCheckError('PROTOCOL', '검증 결과 형식이 올바르지 않습니다.'); result = event.result;}
  }
  try {
    while (true) {
      options.signal?.throwIfAborted();
      const {done, value} = await reader.read();
      options.signal?.throwIfAborted();
      buffer += decoder.decode(value, {stream: !done});
      if (buffer.length > 2_000_000) throw new FactCheckError('PROTOCOL', '검증 스트림이 너무 큽니다.');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n')) >= 0) {line(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 1);}
      if (done) break;
    }
    line(buffer);
    if (!result) throw new FactCheckError('INCOMPLETE', '검증 완료 전에 연결이 종료되었습니다. 다시 시도해 주세요.');
    return result;
  } finally {options.signal?.removeEventListener('abort', abort); await reader.cancel().catch(()=>{}); reader.releaseLock();}
}
