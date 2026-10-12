"use client";

import { AnimatePresence, MotionConfig, motion, useReducedMotion } from 'motion/react';
import { useEffect, useReducer, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, ReactNode } from 'react';
import { initialState, transition } from './demo-state';
import type { Claim } from './demo-state';
import { MODEL_OPTIONS } from '../lib/fact-check-contract';
import type { AgentStage, AnswerBlock, AttachedImage, ContentSummary, FactCheckAnswer, FactCheckRequest, FactCheckResult, FactSource, ModelOption, ModelPreference, ProgressClaim, ProgressSource } from '../lib/fact-check-contract';
import { sourceDiscoveryLabel } from '../lib/source-discovery';
import { scoreBand, scoreLabel } from '../lib/fact-score';
import { stripYoutubeApiDataForExport } from '../lib/youtube-context';
import { FactCheckError, faviconUrlFor, readFactCheckStream, safeSourceUrl, validResult } from './fact-check-client';
import { composeAssistantReply, createAnswerCitationDisplayState, modelLabel as modelNameLabel, presentAnswerCitations } from './fact-check-reply';
import { classifyChatInput, describeHistory, isFollowUpText, isIdentityQuestion, isSummarizeRequest, metaReply } from './chat-intent';
import { DEMO_FOCUS, DEMO_TEXT, demoPreview, documents } from './demo-fixture';
import ScrambleText from './scramble-text';
import StockChart from './stock-chart';
import FloatingLinesBackground from './floating-lines-background';
import LineSidebar from './line-sidebar';
import CountUp from './count-up';
import DonutChart from './donut-chart';
import LatticeLoader from './lattice-loader';
import BlurText from './blur-text';
import { useSpotlight } from './spotlight';
import TechText from './tech-text';
import BorderGlow from './border-glow';
import ConversationHistory from './conversation-history';
import {useConversationStorage} from './use-conversation-storage';
import {writeStorageConsent} from './conversation-consent';
import {toStoredMessage} from './conversation-message';
import {restoreSnapshot} from '../lib/conversation-contract';
import type {MessagePage,StoredMessage} from '../lib/conversation-contract';
import BellToggle from './bell-toggle';
import GlideSelect from './glide-select';
import type { GlideSelectOption } from './glide-select';

type IconName = 'lens' | 'grid' | 'book' | 'arrow' | 'file' | 'link' | 'close' | 'download' | 'plus' | 'shield' | 'check' | 'reset';

function Icon({name, size = 18}: {name: IconName; size?: number}) {
  const paths: Record<IconName, ReactNode> = {
    lens: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5M8 10.5h5M10.5 8v5"/></>,
    grid: <><rect x="4" y="4" width="6" height="6" rx="1"/><rect x="14" y="4" width="6" height="6" rx="1"/><rect x="4" y="14" width="6" height="6" rx="1"/><rect x="14" y="14" width="6" height="6" rx="1"/></>,
    book: <><path d="M12 5v15M12 5C8 2 4 4 3 4v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Z"/></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    file: <><path d="M14 3H5v18h14V8Zm0 0v5h5M8 12h8M8 16h5"/></>,
    link: <><path d="m10 13 4-4M8 15l-2 2a3 3 0 0 1-4-4l5-5a3 3 0 0 1 4 0M13 16a3 3 0 0 0 4 0l5-5a3 3 0 0 0-4-4l-2 2"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    download: <path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    reset: <><path d="M3 5v5h5M3 10a9 9 0 1 1 1 8"/></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Badge({claim}: {claim: Claim}) {
  const mark = claim.scoreBand === 'verified' ? '✓' : claim.scoreBand === 'false' ? '×' : '!';
  return <span className={`badge score-${claim.scoreBand}`}><span aria-hidden="true">{mark}</span>{claim.scoreLabel}</span>;
}

function formatCheckedAt(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '시간 확인 불가';
  const time = new Intl.DateTimeFormat('ko-KR', {timeZone: 'Asia/Seoul', hour: 'numeric', minute: '2-digit', hour12: true}).format(date);
  const day = new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit'}).format(date);
  return `${time}\n${day}`;
}

function formatCheckedAtInline(value: string) {
  return formatCheckedAt(value).replace('\n', ' · ');
}

function TrustIndex({score, claimCount, sourceCount, evidenceCount, warningCount, claims, selectedClaimId, onSelectClaim}: {score: number | null; claimCount: number; sourceCount: number; evidenceCount: number; warningCount: number; claims: readonly Claim[]; selectedClaimId?: string; onSelectClaim: (id: string) => void}) {
  const band = score === null ? 'neutral' : scoreBand(score);
  const [claimMenuOpen, setClaimMenuOpen] = useState(false);
  const [claimMenuPinned, setClaimMenuPinned] = useState(false);
  return <div className={`trust-index ${score === null ? 'is-empty' : ''}`} data-score-band={band}>
      <div className="trust-index-head">
        <div><span className="metric-label">종합 신뢰지수</span><h3 className="fact-score-title"><ScrambleText>팩트 점수</ScrambleText></h3></div>
        <FactScoreGuide score={score}/>
      </div>
    {claims.length > 1 && <div className="claim-score-control" onMouseEnter={() => {if (!claimMenuPinned) setClaimMenuOpen(true);}} onMouseLeave={() => {if (!claimMenuPinned) setClaimMenuOpen(false);}} onFocus={() => setClaimMenuOpen(true)} onBlur={event => {if (!event.currentTarget.contains(event.relatedTarget as Node | null) && !claimMenuPinned) setClaimMenuOpen(false);}}>
      <button type="button" className={`claim-score-trigger ${claimMenuPinned ? 'is-pinned' : ''}`} aria-haspopup="true" aria-expanded={claimMenuOpen} aria-pressed={claimMenuPinned} onClick={() => {const nextPinned = !claimMenuPinned; setClaimMenuPinned(nextPinned); setClaimMenuOpen(nextPinned);}}><Icon name="grid" size={15}/>주장별 점수</button>
      {claimMenuOpen && <div className="claim-score-popover" id="claim-score-popover" role="region" aria-label="주장별 점수">
        {claims.map((claim, index) => <button type="button" key={claim.id} className={`claim-score-option ${selectedClaimId === claim.id ? 'is-selected' : ''}`} aria-pressed={selectedClaimId === claim.id} onClick={() => {onSelectClaim(claim.id); if (!claimMenuPinned) setClaimMenuOpen(false);}}>
          <span className="claim-score-option-index">주장 {String(index + 1).padStart(2, '0')}</span><span className="claim-score-option-verdict"><span className="claim-score-option-verdict-label">판정</span><Badge claim={claim}/></span><span className="claim-score-option-quote">{claim.quote}</span><span className="claim-score-option-value">{claim.factScore}<small>점</small></span>
        </button>)}
      </div>}
    </div>}
    <div className="trust-index-main">
      <DonutChart size={148} progress={score ?? 0} label={score === null ? '검증 대기 중' : `종합 신뢰지수 ${score}점`}>
        {score === null
          ? <span className="donut-chart-empty">대기</span>
          : <CountUp key={`trust-${score}`} from={0} to={score} duration={1.2}/>}
      </DonutChart>
      <div className="trust-copy">
        {score !== null && <span className={`score-label score-${band}`}>{scoreLabel(score)}</span>}
        <strong>{score === null ? '검증을 시작하면 지수가 표시됩니다.' : '주장별 점수의 평균입니다.'}</strong>
        <p>{score === null ? '원문을 보내면 주장, 출처, 인용을 한 화면에서 연결해 볼 수 있습니다.' : '출처의 개수만으로 점수를 올리지 않고, 확인된 인용과 남은 불확실성을 함께 반영합니다.'}</p>
      </div>
    </div>
    <div className="dashboard-stats" aria-label="검증 요약">
      <div><span>검증 주장</span><strong>{claimCount}</strong></div>
      <div><span>검토 출처</span><strong>{sourceCount}</strong></div>
      <div><span>연결 근거</span><strong>{evidenceCount}</strong></div>
      <div><span>확인 필요</span><strong>{warningCount}</strong></div>
    </div>
  </div>;
}

type ChatProgress = {
  status?: string; statusStage?: AgentStage;
  sourcesFound?: ProgressSource[]; sourcesFoundElapsedSeconds?: number;
  sourcesRead?: ProgressSource[]; sourcesReadElapsedSeconds?: number;
  claims?: ProgressClaim[]; claimsElapsedSeconds?: number; completed?: boolean; error?: string;
};
type ChatMessage = {id: string; role: 'assistant' | 'user'; text?: string; answer?: FactCheckAnswer; factScore?: number | null; verdict?: string | null; search?: string | null; scoreMode?: 'jev' | 'claims'; scoreEngine?: string | null; sources?: FactSource[]; progress?: ChatProgress; summary?: ContentSummary; meta?: string; tone?: 'normal' | 'error'; imagePreview?: string; thinking?: boolean; storageStatus?: 'cancelled'};
type ModelSelection = ModelPreference;

function ThinkingLoader({label}: {label: string}) {
  return <span className="chat-loader-row" role="status" aria-label={label}><LatticeLoader label="검증 중" doneLabel="검증 완료" errorLabel="검증 실패" pattern="orbit" grid={3} shape="round" cellSize={7} gap={3} fontSize={12} step={75} idleOpacity={0.15} glow color="#ffffff" showTimer/><span>{label}</span></span>;
}

function SummaryReply({summary}: {summary: ContentSummary}) {
  const href = summary.sourceUrl ? safeSourceUrl(summary.sourceUrl) : null;
  return <section className="summary-reply" aria-label="내용 요약">
    <div className="ai-answer-heading"><span className="answer-spark" aria-hidden="true">✦</span><h3><ScrambleText>요약</ScrambleText></h3></div>
    <h4>{summary.title}</h4>
    <p>{summary.summary}</p>
    {summary.points.length > 0 && <ul className="summary-points">{summary.points.map((point, index) => <li key={index}>{point}</li>)}</ul>}
    {href && <p><a className="answer-citation-chip" href={href} target="_blank" rel="noopener noreferrer"><span className="answer-citation-title">{summary.sourceName || '원문 열기'}</span><span aria-hidden="true">↗</span></a></p>}
    <p className="source-caption">원문 내용 정리입니다. 사실 검증이 아닙니다.</p>
  </section>;
}
const WELCOME_MESSAGE: ChatMessage = {id: 'welcome', role: 'assistant', text: '확인하고 싶은 주장이나 원문을 보내주세요. 문장을 나누고, 직접 확인할 수 있는 출처와 인용을 연결하겠습니다.'};
const EXTERNAL_CONSENT_KEY = 'ton_external_consent';
const EXTERNAL_CONSENT_VERSION = '2026-10-05-v2';

function readExternalConsent() {
  try { return localStorage.getItem(EXTERNAL_CONSENT_KEY) === EXTERNAL_CONSENT_VERSION; }
  catch { return false; }
}

function Modal({open, title, onClose, children, footer}: {open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open && !ref.current?.open) ref.current?.showModal();
    else if (!open && ref.current?.open) ref.current.close();
  }, [open]);
  return <dialog ref={ref} className="dialog" aria-labelledby="dialog-heading" onClose={onClose} onClick={event => {if (event.target === event.currentTarget) onClose();}}>
    <div className="dialog-head"><span className="eyebrow">True or Not · 근거 워크스페이스</span><button className="icon-button" onClick={onClose} aria-label="대화상자 닫기"><Icon name="close"/></button></div>
    <h2 id="dialog-heading">{title}</h2>{children}{footer ?? <button className="secondary-button dialog-done" onClick={onClose}>확인했습니다</button>}
  </dialog>;
}

type PanelProps = {as?: 'div' | 'section' | 'article'; className?: string; children: ReactNode; 'aria-labelledby'?: string};
function Panel({as = 'div', className = '', children, 'aria-labelledby': labelledBy}: PanelProps) {
  const Element = as;
  return <Element className={`panel-host ${className}`} aria-labelledby={labelledBy}>{children}</Element>;
}

function AnswerBlockView({block, sources, citationState}: {block: AnswerBlock; sources: FactSource[]; citationState: ReturnType<typeof createAnswerCitationDisplayState>}) {
  const citations = presentAnswerCitations(block.citations, sources, citationState);
  return <div className="answer-block">
    <p className="answer-block-text">{block.text}</p>
    {citations.length > 0 && <ul className="answer-citations" aria-label="답변 근거 출처">
      {citations.map(({number, source, href, linkTarget}, index) => <li key={`${number}-${index}`}>
          {linkTarget === 'external' && source && href
            ? <a className="answer-citation-chip" href={href} target="_blank" rel="noopener noreferrer" title={source.title} aria-label={`출처 ${number}: ${source.title} (${source.publisher}). 새 탭에서 원문 열기`}>
                <span className="answer-citation-index">[{number}]</span><span className="answer-citation-title">{source.title}</span><span aria-hidden="true">↗</span>
              </a>
              : <span className="answer-citation-chip is-unavailable" aria-label={`출처 ${number}: 확인된 원문 연결 없음`}>
                <span className="answer-citation-index">[{number}]</span><span className="answer-citation-title">확인된 원문 링크 없음</span>
              </span>}
        </li>)}
    </ul>}
  </div>;
}

function AnswerOverview({answer, sources}: {answer: FactCheckAnswer; sources: FactSource[]; messageId: string}) {
  const citationState = createAnswerCitationDisplayState(sources);
  return <section className="ai-answer" aria-label="AI 개요">
    <div className="ai-answer-heading"><span className="answer-spark" aria-hidden="true">✦</span><h3 className="ai-overview-title"><ScrambleText>AI 개요</ScrambleText></h3></div>
    {answer.status === 'insufficient_evidence'
      ? <p className="answer-insufficient" role="note">확인된 원문 근거가 부족해 AI 개요를 만들지 않았습니다. 아래 출처 목록과 주장별 판정에서 확인 가능한 내용을 살펴보세요.</p>
      : <>
          {answer.overview && <div className="answer-overview-block"><AnswerBlockView block={answer.overview} sources={sources} citationState={citationState}/></div>}
          {answer.sections.map((section, sectionIndex) => <section className={`answer-section answer-section--${section.kind}`} key={`${section.kind}-${sectionIndex}`} aria-label={section.title}>
            <h4><ScrambleText>{section.title}</ScrambleText></h4>
            <ul className="answer-section-items">{section.items.map((item, itemIndex) => <li key={itemIndex}><AnswerBlockView block={item} sources={sources} citationState={citationState}/></li>)}</ul>
          </section>)}
          {answer.conclusion && <section className="answer-conclusion" aria-label="정리">
            <h4><ScrambleText>정리</ScrambleText></h4><AnswerBlockView block={answer.conclusion} sources={sources} citationState={citationState}/>
          </section>}
        </>}
  </section>;
}

const FACT_SCORE_GUIDE_ROWS = [
  {band: 'verified', range: '80–100', label: '검증된 사실', meaning: '근거가 강하게 지지'},
  {band: 'mostly_true', range: '60–79', label: '대체적으로 사실', meaning: '지지 근거가 우세'},
  {band: 'neutral', range: '40–59', label: '중립', meaning: '엇갈리거나 불충분'},
  {band: 'mostly_false', range: '20–39', label: '대체적으로 거짓', meaning: '반박 근거가 우세'},
  {band: 'false', range: '0–19', label: '거짓', meaning: '근거가 강하게 반박'},
] as const;

function FactScoreGuide({score}: {score?: number | null}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const open = hovered || focused;
  const currentBand = typeof score === 'number' ? scoreBand(score) : null;
  return <div
    className={`fact-score-guide${open ? ' is-open' : ''}`}
    onMouseEnter={() => setHovered(true)}
    onMouseLeave={() => setHovered(false)}
    onFocusCapture={() => setFocused(true)}
    onBlurCapture={() => setFocused(false)}
  >
    <button className="fact-score-guide-button" type="button" aria-expanded={open}>
      <span aria-hidden="true">ⓘ</span> 점수 기준
    </button>
    {open && <div className="fact-score-guide-popover" role="region" aria-label="팩트 점수 기준">
      <h4><ScrambleText>점수 기준</ScrambleText></h4>
      <table>
        <thead><tr><th>점수</th><th>판정 범위</th><th>읽는 방법</th></tr></thead>
        <tbody>{FACT_SCORE_GUIDE_ROWS.map(row => <tr key={row.band} className={row.band === currentBand ? 'is-current' : undefined}>
          <td>{row.range}</td><td>{row.label}</td><td>{row.meaning}</td>
        </tr>)}</tbody>
      </table>
      <p>점수는 사실일 확률이 아니라, 확인된 근거가 주장을 지지하는 정도에 대한 AI 평가입니다. 평균 점수는 전체 원문의 사실 여부를 뜻하지 않습니다.</p>
    </div>}
  </div>;
}

function JevFactScore({score, verdict, search, engine}: {score: number | null; verdict?: string | null; search?: string | null; engine?: string | null}) {
  const label = engine ?? (search ? `JEV+${search.replace(' 검색', '')}` : 'JEV');
  return <section className="jev-score-reply" aria-label={score === null ? '팩트 점수 없음' : `팩트 점수 ${score}점${verdict ? `, ${verdict}` : ''}`}>
    <div className="jev-score-heading">
      <span className="jev-score-label">팩트 점수 · {label}{verdict ? ` · ${verdict}` : ''}</span>
      {score !== null && <span className={`badge score-${scoreBand(score)}`}>{scoreLabel(score)}</span>}
    </div>
    <div className="jev-score-result">
      <strong className="jev-score-value">{score ?? '—'}<span>점</span></strong>
    </div>
  </section>;
}

function JevSourceList({sources}: {sources: FactSource[]}) {
  if (!sources.length) return null;
  return <ul className="jev-source-list" aria-label="JEV 검증 출처">{
    sources.map((source, index) => {
      const href = safeSourceUrl(source.url);
      const icon = faviconUrlFor(source.url);
      return <li key={source.id}>
        <span className="progress-source-index">[{index + 1}]</span>
        {icon && <img className="progress-source-favicon" src={icon} alt="" width={12} height={12} loading="lazy" onError={event => {event.currentTarget.hidden = true;}}/>}
        {href
          ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title}</a>
          : <strong>{source.title}</strong>}
      </li>;
    })
  }</ul>;
}

const VERIFY_STAGES: Array<{id: AgentStage; label: string}> = [
  {id: 'extracting', label: '추출'},
  {id: 'searching', label: '검색'},
  {id: 'reading', label: '읽기'},
  {id: 'verifying', label: '검증'},
  {id: 'synthesizing', label: '합성'},
];

function VerifyTimeline({progress}: {progress: ChatProgress}) {
  const currentIndex = progress.completed
    ? VERIFY_STAGES.length
    : Math.max(0, VERIFY_STAGES.findIndex(stage => stage.id === progress.statusStage));
  const visibleStages = VERIFY_STAGES.slice(0, Math.min(VERIFY_STAGES.length, Math.max(3, currentIndex + 1)));
  const [travel, setTravel] = useState<{from: number; to: number; key: number} | null>(null);
  const prevRef = useRef(currentIndex);
  useEffect(() => {
    const from = prevRef.current;
    const to = Math.min(currentIndex, visibleStages.length - 1);
    prevRef.current = currentIndex;
    if (to <= from) {
      setTravel(null);
      return;
    }
    const key = from * 10 + to;
    setTravel({from, to, key});
    const timer = setTimeout(() => setTravel(active => active?.key === key ? null : active), 900);
    return () => clearTimeout(timer);
  }, [currentIndex, visibleStages.length]);
  if (!progress.statusStage && !progress.completed && !progress.error) return null;
  return <ol className="verify-timeline" aria-label="검증 단계 진행">
    {visibleStages.map((stage, index) => <li key={stage.id} data-state={index < currentIndex ? 'done' : index === currentIndex ? 'active' : 'todo'}><span className="verify-timeline-dot" aria-hidden="true"/><span>{stage.label}</span></li>)}
    {travel && <span key={travel.key} className="verify-traveler" aria-hidden="true" style={{'--travel-from': `${((travel.from + 0.5) / visibleStages.length) * 100}%`, '--travel-width': `${((travel.to - travel.from) / visibleStages.length) * 100}%`} as CSSProperties}/>}
  </ol>;
}

function ProgressReply({progress}: {progress: ChatProgress}) {
  const [stageElapsedSeconds, setStageElapsedSeconds] = useState(0);
  useEffect(() => {
    if (progress.completed || progress.error) return;
    const startedAt = performance.now();
    setStageElapsedSeconds(0);
    const timer = window.setInterval(() => {
      setStageElapsedSeconds(Math.floor((performance.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [progress.statusStage, progress.completed, progress.error]);
  const claims = progress.claims;
  const sources = progress.sourcesRead ?? [];
  const sourceNumbers = new Map(sources.map((source, index) => [source.id, index + 1]));
  const heading = claims !== undefined ? '1차 검증 요약' : '검증 진행 상황';
  return <section className="progress-reply" data-testid="progress-reply" aria-label="검증 진행 결과">
    <div className="progress-reply-heading"><span aria-hidden="true">✦</span><h3><ScrambleText>{heading}</ScrambleText></h3><span className="progress-reply-status">{progress.error ? '중단' : progress.completed ? '완료' : '중간 업데이트'}</span></div>
    {!progress.completed && !progress.error && <ThinkingLoader label={progress.status ?? '최종 답변을 만드는 중입니다.'}/>}
    <VerifyTimeline progress={progress}/>
    {progress.status && <p className="progress-current-stage" data-testid="progress-stage">
      <span>{progress.status}</span><time>{stageElapsedSeconds}초 경과</time>
    </p>}
    {progress.sourcesFound !== undefined && progress.sourcesRead === undefined && <ProgressSourceList title="검색된 출처 후보" sources={progress.sourcesFound} elapsedSeconds={progress.sourcesFoundElapsedSeconds} testId="progress-candidate-source"/>}
    {progress.sourcesRead !== undefined && <ProgressSourceList title="가져온 원문" sources={progress.sourcesRead} elapsedSeconds={progress.sourcesReadElapsedSeconds} testId="progress-read-source"/>}
    {claims !== undefined && (claims.length
      ? <ol className="progress-claim-list">{claims.map(claim => <li className="progress-claim" key={claim.id}>
          <div className="progress-claim-heading"><strong>{claim.quote}</strong><span>{claim.verdict}</span></div>
          <p>{claim.summary}</p>
          {claim.citations.length > 0 && <ul className="progress-citations" aria-label="1차 요약의 확인된 인용">{claim.citations.map((citation, index) => {
            const source = sources.find(item => item.id === citation.sourceId);
            const href = source ? safeSourceUrl(source.url) : null;
            const number = sourceNumbers.get(citation.sourceId) ?? index + 1;
            return <li key={`${claim.id}-${citation.sourceId}-${index}`}>{source && href
              ? <a href={href} target="_blank" rel="noopener noreferrer" title={citation.quote} aria-label={`출처 ${number}: ${source.publisher}, ${source.title}`}>
                  <span>[{number}]</span> {source.title}
                </a>
              : <span className="progress-citation-unavailable">인용 출처 확인 필요</span>}</li>;
          })}</ul>}
        </li>)}</ol>
        : <p className="progress-empty">검증 가능한 주장을 찾지 못했습니다. 확인할 원문·링크·이미지를 보내주시면 검증하겠습니다.</p>)}
        {claims !== undefined && progress.claimsElapsedSeconds !== undefined && <small className="progress-milestone-time">1차 요약 · {progress.claimsElapsedSeconds}초</small>}
        {progress.error
          ? <p className="progress-error" role="alert">{progress.error}<br/>위 내용은 최종 답변이 아닌 1차 확인 결과입니다.</p>
          : <small className="progress-disclaimer">{progress.completed ? '검증 진행 기록입니다. 최종 답변은 아래에 이어집니다.' : '최종 인용 답변을 만드는 중입니다. 이 1차 요약은 완성된 답변이 아닙니다.'}</small>}
        </section>;
        }

        function ProgressSourceList({title, sources, elapsedSeconds, testId}: {title: string; sources: ProgressSource[]; elapsedSeconds?: number; testId: string}) {
        return <div className="progress-source-block" data-testid={`${testId}-group`}>
        <h4><ScrambleText>{title}</ScrambleText>{elapsedSeconds !== undefined && <span className="progress-milestone-time"> · {elapsedSeconds}초</span>}</h4>
        {sources.length > 0
        ? <ul className="progress-source-list">{sources.map((source, index) => {
            const href = safeSourceUrl(source.url);
            const icon = faviconUrlFor(source.url);
            const accessLabel = source.accessStatus === 'candidate' ? '검색 후보' : source.accessStatus === 'verified' ? '원문 확인' : '접근 불가';
            return <li className="progress-source" key={source.id} data-testid={testId}>
              <span className="progress-source-index">[{index + 1}]</span>
              <span className="progress-source-copy"><span className="progress-source-title-row">{icon && <img className="progress-source-favicon" src={icon} alt="" width={14} height={14} loading="lazy" onError={event => {event.currentTarget.hidden = true;}}/>}{href
                ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title}</a>
                : <strong>{source.title}</strong>}</span><small>{source.publisher} · {source.sourceType} · {accessLabel}</small></span>
            </li>;
          })}</ul>
        : <p className="progress-empty">이 단계에서 확인된 출처가 없습니다. 다음 검증 단계를 진행하고 있습니다.</p>}
        </div>;
        }

export default function FactCheckDashboard() {
  const reduce = useReducedMotion();
  const [state, dispatch] = useReducer(transition, initialState);
  const [draft, setDraft] = useState('');
  const [focus, setFocus] = useState('');
  const [sample, setSample] = useState(false);
  const [mobileTab, setMobileTab] = useState('results');
  const [dialog, setDialog] = useState<string | null>(null);
  const [externalConsent, setExternalConsent] = useState(false);
  const [storageConsentDraft, setStorageConsentDraft] = useState(false);
  const [storagePreferenceSaved, setStoragePreferenceSaved] = useState(true);
  const externalConsentRef = useRef(false);
  const screenConsent = useRef(false);
  const pendingConsent = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const [notice, setNotice] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const storage = useConversationStorage();
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const messageCounter = useRef(0);
  const cancelNoticed = useRef(false);
  const [image, setImage] = useState<{mime: AttachedImage['mime']; data: string; preview: string} | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [jevConfigured, setJevConfigured] = useState<boolean | null>(null);
  const [configuredModel, setConfiguredModel] = useState<string | null>(null);
  const [modelOptions, setModelOptions] = useState<ModelOption[]>([]);
  const [modelSelection, setModelSelection] = useState<ModelSelection>('auto');
  const [jevMode, setJevMode] = useState(false);
  const modelPreference: ModelPreference = modelSelection;
  const [configError, setConfigError] = useState(false);
  const [liveResult, setLiveResult] = useState<FactCheckResult | null>(null);
  const spotlight = useSpotlight<HTMLElement>();
  const editor = useRef<HTMLTextAreaElement>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const [atBottom, setAtBottom] = useState(true);
  const [scrolled, setScrolled] = useState(false);
  const handleThreadScroll = () => {
    const el = threadRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    stickToBottom.current = near;
    setAtBottom(near);
    setScrolled(el.scrollTop > 8);
  };
  const scrollThreadToBottom = () => {
    const el = threadRef.current;
    if (!el) return;
    el.scrollTo({top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth'});
  };
  const snapshot = state.snapshot;
  const selected = snapshot?.claims.find(claim => claim.id === state.selectedId);
  const sourceDocs = snapshot?.demo && selected ? documents.filter(document => selected.evidenceIds.includes(document.id)) : [];
  const activeDocument = documents.find(document => document.id === dialog);
  const busy = state.status === 'loading';
  useEffect(() => {
    const refreshConsent = () => {
      const accepted = readExternalConsent();
      screenConsent.current = false;
      externalConsentRef.current = accepted;
      setExternalConsent(accepted);
      if (!accepted && request.current) cancelVerification();
    };
    refreshConsent();
    const changed = (event: StorageEvent) => {
      if (event.key === EXTERNAL_CONSENT_KEY || event.key === null) refreshConsent();
    };
    window.addEventListener('storage', changed);
    return () => window.removeEventListener('storage', changed);
  }, []);
  useEffect(() => {
    if (!stickToBottom.current) return;
    stickToBottom.current = false;
    setAtBottom(true);
    scrollThreadToBottom();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, busy]);
  const configurationHelp = '서버 설정이 필요합니다. backend/.env 또는 백엔드 실행 환경에 EXPLABS_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY 또는 AI_GATEWAY_API_KEY를 설정한 뒤 서버를 다시 시작해 주세요. 키를 화면이나 채팅에 입력하지 마세요.';
  const serviceLabel = configured === true ? 'LLM fallback 설정됨 · 접근 미확인' : configured === false ? 'LLM 키 미설정' : configError ? '설정 확인 실패' : '서버 설정 확인 중';
  const modelLabel = MODEL_OPTIONS.find(model => model.id === configuredModel)?.label
    ?? (configured === false ? '모델 미설정' : '모델 확인 중');
  const fallbackOrder = modelOptions.filter(model => model.configured).map(model => model.label).join(' → ');
  const modelPickerOptions: GlideSelectOption[] = [
    {value: 'auto', label: 'Auto', tag: 'Fallback', disabled: configured !== true},
    ...modelOptions.map(model => ({
      value: model.id,
      label: model.label,
      tag: model.id.startsWith('deepseek-') ? 'Experiential' : model.id.startsWith('gemini-') ? 'Gemini' : 'OpenAI',
      disabled: !model.configured,
    })),
  ];
  const attachImage = (attached: NonNullable<typeof image>) => {
    if (jevMode) {
      setJevMode(false);
      setNotice('이미지는 JEV에서 지원하지 않아 껐어.');
    }
    setImage(attached);
  };
  
  const sourceCount = snapshot ? snapshot.demo ? documents.length : liveResult?.sources.length ?? 0 : 0;
  const evidenceCount = snapshot ? snapshot.demo ? snapshot.claims.reduce((total, claim) => total + claim.evidenceIds.length, 0) : liveResult?.evidence.length ?? 0 : 0;
  const trustScore = snapshot?.claims.length ? Math.round(snapshot.claims.reduce((total, claim) => total + claim.factScore, 0) / snapshot.claims.length) : null;
  const warningCount = snapshot ? snapshot.demo ? snapshot.claims.filter(claim => claim.scoreBand !== 'verified').length : liveResult?.warnings.length ?? 0 : 0;
  const selectedEvidence = selected && liveResult ? liveResult.evidence.filter(evidence => evidence.claimId === selected.id && selected.evidenceIds.includes(evidence.id)) : [];
  const selectedSourceIds = new Set(snapshot?.demo ? sourceDocs.map(source => source.id) : selectedEvidence.map(evidence => evidence.sourceId));
  const selectedLiveClaim = selected && liveResult ? liveResult.claims.find(claim => claim.id === selected.id) : null;

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/fact-check', {signal: controller.signal, cache: 'no-store'})
      .then(async response => {
        if (!response.ok) throw new Error();
        const status = await response.json();
        if (typeof status.configured !== 'boolean' || typeof status.jevConfigured !== 'boolean' || !Array.isArray(status.modelOptions)) throw new Error();
        const options: ModelOption[] = MODEL_OPTIONS.map(model => {
          const option = status.modelOptions.find((candidate: unknown) => candidate && typeof candidate === 'object' && 'id' in candidate && candidate.id === model.id);
          if (!option || typeof option.configured !== 'boolean') throw new Error();
          return {...model, configured: option.configured};
        });
        if (!controller.signal.aborted) {
          setConfigured(status.configured);
          setJevConfigured(status.jevConfigured);
          setConfiguredModel(typeof status.model === 'string' ? status.model : null);
          setModelOptions(options);
        }
      })
      .catch(() => {if (!controller.signal.aborted) setConfigError(true);});
    return () => {controller.abort(); generation.current++; request.current?.abort();};
  }, []);

  function saveChat(message: Omit<ChatMessage,'id'>, epoch: number, result?:FactCheckResult) {
    const stored = toStoredMessage(message,result);
    if(stored)void storage.saveMessage(stored,epoch);
  }

  function addMessage(message: Omit<ChatMessage, 'id'>, epoch=storage.epoch) {
    const id = `message-${messageCounter.current++}`;
    setMessages(current => [...current, {...message, id}]);
    saveChat(message,epoch);
    return id;
  }

  function stop() {
    generation.current++;
    request.current?.abort();
    request.current = null;
  }

  function cancelVerification() {
    if (request.current) cancelNoticed.current = true;
    stop();
    dispatch({type: 'cancel'});
    setMessages(messages => messages.filter(message => !message.thinking));
    setNotice('검증을 중단했습니다.');
    addMessage({role:'assistant',text:'검증을 중단했습니다.',storageStatus:'cancelled'});
  }

  function openConsentDialog(kind: 'external-consent' | 'storage-consent') {
    setStorageConsentDraft(storage.consent);
    setDialog(kind);
  }

  function applyStorageConsent() {
    setStoragePreferenceSaved(writeStorageConsent(storageConsentDraft));
    if (storage.consent !== storageConsentDraft) storage.setConsent(storageConsentDraft);
  }

  function acceptExternalConsent() {
    screenConsent.current = false;
    try { localStorage.setItem(EXTERNAL_CONSENT_KEY, EXTERNAL_CONSENT_VERSION); }
    catch { screenConsent.current = true; setNotice('브라우저 저장이 차단되어 전송 동의는 현재 화면에서만 유지됩니다.'); }
    externalConsentRef.current = true;
    setExternalConsent(true);
    applyStorageConsent();
    const resume = pendingConsent.current;
    pendingConsent.current = false;
    setDialog(null);
    if (resume) form.current?.requestSubmit();
  }

  function revokeExternalConsent() {
    try { localStorage.removeItem(EXTERNAL_CONSENT_KEY); }
    catch { setNotice('동의를 철회했습니다. 브라우저에 남은 동의 기록도 사이트 데이터 설정에서 삭제해 주세요.'); }
    externalConsentRef.current = false;
    screenConsent.current = false;
    setExternalConsent(false);
    pendingConsent.current = false;
    if (request.current) cancelVerification();
  }

  function hasExternalConsent() {
    const accepted = externalConsentRef.current && (screenConsent.current || readExternalConsent());
    if (!accepted && externalConsentRef.current) {
      externalConsentRef.current = false;
      setExternalConsent(false);
    }
    return accepted;
  }

  function requireExternalConsent() {
    if (!hasExternalConsent()) throw new FactCheckError('CONSENT_REQUIRED', '외부 서비스 전송에 다시 동의해 주세요.');
  }

  function firstUrl(text: string): string | null {
    const match = text.match(/https?:\/\/[^\s)\]]+/);
    if (!match) return null;
    return safeSourceUrl(match[0].replace(/[.,;:!?)\]]+$/, ''));
  }

  async function downscaleImage(file: File): Promise<{mime: 'image/jpeg'; data: string; preview: string} | null> {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {setNotice('JPEG·PNG·WebP 이미지만 보낼 수 있습니다.'); return null;}
    if (file.size > 8_000_000) {setNotice('이미지는 8MB 이하로 보내 주세요.'); return null;}
    const bitmap = await createImageBitmap(file).catch(() => null);
    if (!bitmap) {setNotice('이미지를 읽을 수 없습니다.'); return null;}
    const scale = Math.min(1, 1568 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) {bitmap.close(); setNotice('이미지를 읽을 수 없습니다.'); return null;}
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const preview = canvas.toDataURL('image/jpeg', 0.82);
    const data = preview.split(',', 2)[1] ?? '';
    if (!data || data.length > 1500000) {setNotice('이미지가 너무 큽니다. 더 작은 이미지로 보내 주세요.'); return null;}
    return {mime: 'image/jpeg', data, preview};
  }

  const detectedLink = firstUrl(draft);

  type GateDecision = {action: 'verify' | 'reply'; reply: string | null; focus: string | null};
  function gateContext() {
    return {
      previousText: liveResult?.text.slice(0, 2000) ?? null,
      previousClaims: liveResult?.claims.slice(0, 3).map(claim => ({quote: claim.quote.slice(0, 200), verdict: claim.verdict, score: claim.factScore})) ?? [],
      recentUser: messages.filter(message => message.role === 'user' && message.text).slice(-3).map(message => message.text!.slice(0, 200)),
    };
  }
  async function requestGate(text: string, model: ModelPreference, consent: true, signal: AbortSignal): Promise<GateDecision> {
    requireExternalConsent();
    const response = await fetch('/api/intent', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({text, context: gateContext(), consent, modelPreference: model}), signal});
    if (!response.ok) throw new Error('INTENT_FAILED');
    const value = await response.json() as {action?: unknown; reply?: unknown; focus?: unknown};
    requireExternalConsent();
    if (value?.action !== 'verify' && value?.action !== 'reply') throw new Error('INTENT_FAILED');
    if (value.action === 'reply' && typeof value.reply !== 'string') throw new Error('INTENT_FAILED');
    return {action: value.action, reply: typeof value.reply === 'string' ? value.reply : null, focus: typeof value.focus === 'string' ? value.focus : null};
  }
  async function requestSummary(text: string, focus: string, linkUrl: string | null, consent: boolean, signal: AbortSignal): Promise<ContentSummary> {
    requireExternalConsent();
    if (!consent) throw new FactCheckError('CONSENT_REQUIRED', '외부 서비스 전송에 먼저 동의해 주세요.');
    const response = await fetch('/api/summarize', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({text, focus, consent, modelPreference, ...(linkUrl ? {linkUrl} : {})}), signal});
    if (!response.ok) {
      const error = await response.json().catch(()=>null);
      throw new FactCheckError(typeof error?.code === 'string' ? error.code : 'HTTP_ERROR', typeof error?.message === 'string' ? error.message : `요약 요청에 실패했습니다 (${response.status}).`);
    }
    const value = await response.json() as {result?: unknown};
    requireExternalConsent();
    const result = value?.result as ContentSummary | undefined;
    if (!result || typeof result.title !== 'string' || typeof result.summary !== 'string' || !Array.isArray(result.points)) throw new FactCheckError('PROTOCOL', '요약 결과 형식이 올바르지 않습니다.');
    return {...result, meta: `${modelNameLabel(result.model ?? null)} · 내용 요약`};
  }
  const prevHasClaims = (liveResult?.claims.length ?? 0) > 0;
  const continuedThread = !sample && !image && !detectedLink && liveResult !== null && isFollowUpText(draft);
  const followUp = continuedThread && prevHasClaims;

  function loadSample() {
    stop();
    storage.newConversation();
    setLiveResult(null);
    dispatch({type: 'cancel'});
    dispatch({type: 'load', snapshot: demoPreview});
    setDraft(DEMO_TEXT);
    setFocus(DEMO_FOCUS);
    setSample(true);
    setImage(null);
    setMessages([
      WELCOME_MESSAGE,
      {id: 'sample-user', role: 'user', text: DEMO_TEXT, meta: `확인 요청: ${DEMO_FOCUS}`},
      {id: 'sample-assistant', role: 'assistant', text: '합성 예시를 준비했습니다. 아래 대시보드에서 주장별 점수와 같은 원자료를 공유하는 출처를 확인해 보세요.', meta: '외부 전송 없음'},
    ]);
    setNotice('가상의 행사 예시를 불러왔습니다. 외부 전송 없이 예시 문서를 비교합니다.');
  }

  function reset() {
    stop();
    storage.newConversation();
    setLiveResult(null);
    setImage(null);
    dispatch({type: 'reset'});
    setDraft('');
    setFocus('');
    setSample(false);
    setMessages([WELCOME_MESSAGE]);
    setNotice('');
    editor.current?.focus();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || request.current || storage.loading) return;
    if (!draft.trim() && !image) {setNotice('검증할 원문이나 이미지를 입력해 주세요.'); return;}
    if (draft.length > 12000 || focus.length > 500) {setNotice('원문은 12,000자, 확인 요청은 500자 이내로 입력해 주세요.'); return;}
    if (sample) {dispatch({type: 'load', snapshot: {...demoPreview, focus}}); setNotice('합성 예시입니다. 실제 검증 요청은 전송하지 않았습니다.'); return;}
    const consent = hasExternalConsent();
    if (!consent && (image || detectedLink || !isIdentityQuestion(draft))) {
      pendingConsent.current = true;
      openConsentDialog('external-consent');
      return;
    }

    stop();
    const storageEpoch = storage.epoch;
    const appendReply = (message:Omit<ChatMessage,'id'>) => addMessage(message,storageEpoch);
    const controller = new AbortController();
    request.current = controller;
    addMessage({role: 'user', text: followUp ? draft.trim() : draft, meta: continuedThread ? '이전 검증에 이어서 확인' : focus ? `확인 요청: ${focus}` : undefined, ...(image ? {imagePreview: image.preview} : {})});
    stickToBottom.current = true;
    const sentDraft = draft;
    setDraft('');
    setFocus('');
    setImage(null);
    const current = generation.current;
    const startedAt = performance.now();
    const elapsedSeconds = () => Math.floor((performance.now() - startedAt) / 1000);
    let progressMessageId: string | null = null;
    const thinkingId = addMessage({role: 'assistant', thinking: true});
    progressMessageId = thinkingId;
    const removeThinking = () => setMessages(messages => messages.filter(message => message.id !== thinkingId));
    const release = () => {if (request.current === controller) request.current = null;};
    const updateProgressMessage = (patch: Partial<ChatProgress>) => {
      if (generation.current !== current) return;
      setMessages(messages => messages.map(message => message.id === progressMessageId
        ? {...message, thinking: false, progress: {...message.progress, ...patch}}
        : message));
    };
    let gate: GateDecision | null = null;
    if (!image && isSummarizeRequest(draft) && (detectedLink || draft.trim().length > 200)) {
      try {
        const reply = await requestSummary(draft, focus.trim(), detectedLink, consent, controller.signal);
        if (generation.current !== current || controller.signal.aborted) {release(); return;}
        removeThinking();
        appendReply({role: 'assistant', summary: reply});
        setNotice('내용을 요약했습니다. 사실 확인은 검증으로 요청해 주세요.');
      } catch (error) {
        if (generation.current !== current || controller.signal.aborted) return;
        removeThinking();
        appendReply({role: 'assistant', text: error instanceof FactCheckError ? `요약 실패: ${error.message}` : '요약 요청에 실패했습니다.', tone: 'error'});
      }
      setDraft(''); setFocus(''); setImage(null); release();
      return;
    }
    if (!image && !detectedLink && isIdentityQuestion(draft)) {
      removeThinking();
      const label = modelSelection === 'auto' ? 'Auto' : (MODEL_OPTIONS.find(model => model.id === modelSelection)?.label ?? modelSelection);
      appendReply({role: 'assistant', text: jevMode ? `현재 ${label} 모드에서 JEV를 함께 사용합니다. 답변 아래에 Jev 점수도 표시됩니다.` : `현재 ${label} 모드입니다.`});
      setDraft(''); setFocus(''); setImage(null); release();
      return;
    }
    if (!consent) {release(); return;}
    if (!image && !detectedLink && draft.trim().length <= 120) {
      try {
        gate = await requestGate(draft.trim(), modelPreference, consent, controller.signal);
      } catch { gate = null; }
      if (generation.current !== current || controller.signal.aborted) {release(); return;}
    }
    if (gate?.action === 'reply' && gate.reply) {
      removeThinking();
      appendReply({role: 'assistant', text: gate.reply});
      setDraft(''); setFocus(''); setImage(null); release();
      return;
    }
    const gateFocus = gate?.action === 'verify' ? (gate.focus || '') : '';
    if (!gate) {
      const fallback = classifyChatInput(draft, {hasPrevious: !sample && liveResult !== null, hasAttachment: !!(image || detectedLink)});
      if (fallback.kind === 'meta') {
        removeThinking();
        appendReply({role: 'assistant', text: fallback.topic === 'history' ? describeHistory(messages, liveResult, DEMO_TEXT) : metaReply(fallback.topic)});
        setDraft(''); setFocus(''); setImage(null); release();
        return;
      }
      if (fallback.kind === 'followup' && !prevHasClaims) {
        removeThinking();
        appendReply({role: 'assistant', text: '이전 검증에서 검증 가능한 주장을 찾지 못했습니다. 확인할 원문·링크·이미지를 보내주시면 바로 검증하겠습니다.'});
        setDraft(''); release();
        return;
      }
    }
    if ((jevMode && jevConfigured !== true) || (!jevMode && configured === false)) {removeThinking(); setNotice(configurationHelp); release(); return;}
    const effectiveText = followUp && liveResult ? liveResult.text : draft;
    const effectiveFocus = followUp
      ? [focus.trim(), gateFocus.trim(), draft.trim()].filter(part => part).join(' / ')
      : [focus.trim(), gateFocus.trim()].filter(part => part).join(' / ');
    const submitted: FactCheckRequest = {text: effectiveText, focus: effectiveFocus, consent, modelPreference, ...(detectedLink && !followUp ? {linkUrl: detectedLink} : {}), ...(image ? {image: {mime: image.mime, data: image.data}} : {})};
    if (!followUp) {
      setLiveResult(null);
      dispatch({type: 'reset'});
    }
    dispatch({type: 'start'});
    setNotice(followUp ? '이전 원문을 유지하고 확인 요청으로 이어서 검증합니다.' : '검증 요청을 서버로 전송하고 있습니다.');
    try {
      const runMain = async () => {
        requireExternalConsent();
        return readFactCheckStream(
        await fetch('/api/fact-check', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(submitted), signal: controller.signal}),
        {
          signal: controller.signal,
          onStage: stage => {
            if (generation.current !== current) return;
            updateProgressMessage({status: stage.message, statusStage: stage.stage});
            setNotice(stage.message);
          },
          onSources: event => {
            if (generation.current !== current) return;
            const elapsed = elapsedSeconds();
            updateProgressMessage(event.phase === 'found'
              ? {sourcesFound: event.sources, sourcesFoundElapsedSeconds: elapsed}
              : {sourcesRead: event.sources, sourcesReadElapsedSeconds: elapsed});
            setNotice(event.phase === 'found'
              ? '검색 결과에서 출처 후보를 찾았습니다. 원문을 읽고 있습니다.'
              : '출처 원문을 가져왔습니다. 주장과 인용을 검증하고 있습니다.');
          },
          onPreview: event => {
            if (generation.current !== current) return;
            updateProgressMessage({claims: event.claims, claimsElapsedSeconds: elapsedSeconds()});
            setNotice('1차 검증을 마쳤습니다. 최종 답변과 인용을 정리하고 있습니다.');
          },
        },
        );
      };
      const runJev = async (): Promise<FactCheckResult> => {
        requireExternalConsent();
        const jevResponse = await fetch('/api/fact-check/jev', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({...submitted, jevMode: true}), signal: controller.signal});
        if (!jevResponse.ok) {
          const error = await jevResponse.json().catch(()=>null);
          throw new FactCheckError(typeof error?.code === 'string' ? error.code : 'HTTP_ERROR', typeof error?.message === 'string' ? error.message : `서버 요청에 실패했습니다 (${jevResponse.status}).`);
        }
        const value: unknown = await jevResponse.json();
        if (!validResult(value)) throw new FactCheckError('PROTOCOL', '검증 결과 형식이 올바르지 않습니다.');
        return value;
      };
      let result: FactCheckResult;
      let jevResult: FactCheckResult | null = null;
      if (jevMode) {
        result = await runJev();
        jevResult = result;
        if (generation.current !== current || controller.signal.aborted) return;
        removeThinking();
        progressMessageId = null;
      } else {
        result = await runMain();
      }
      if (generation.current !== current || controller.signal.aborted) return;
      requireExternalConsent();
      if (!submitted.linkUrl && !submitted.image && (result.text !== submitted.text || result.focus !== submitted.focus)) throw new Error('제출한 원문과 검증 결과가 일치하지 않습니다. 다시 시도해 주세요.');
      setImage(null);
      setDraft('');
      if (followUp && !result.claims.length) {
        setNotice('추가로 확인된 내용이 없어서 이전 결과를 유지합니다.');
      } else {
        setLiveResult(result);
        dispatch({type: 'load', snapshot: result});
      }
      setMobileTab('results');
      if (!(followUp && !result.claims.length)) setNotice(result.claims.length ? '검증이 완료되었습니다. 아래에서 출처와 남은 불확실성을 확인해 주세요.' : '검증 가능한 주장을 찾지 못했습니다. 결과의 경고를 확인해 주세요.');
      const reply = composeAssistantReply(result, jevResult);
      const finalMessage: ChatMessage = {id: `message-${messageCounter.current++}`, role: 'assistant', ...reply};
      saveChat(finalMessage,storageEpoch,result);
      if (progressMessageId) {
        setMessages(messages => [...messages.map(message => message.id === progressMessageId && message.progress
          ? {...message, progress: {...message.progress, status: '검증 완료', completed: true}}
          : message), finalMessage]);
      } else {
        setMessages(messages => [...messages, finalMessage]);
      }
    } catch (error) {
      if (cancelNoticed.current) { cancelNoticed.current = false; return; }
      if (generation.current !== current || controller.signal.aborted) {
        saveChat({role:'assistant', text: controller.signal.aborted ? '검증이 중단되어 결과를 저장하지 못했습니다. 다시 시도해 주세요.' : '검증이 다른 요청으로 대체되어 결과를 저장하지 못했습니다. 다시 시도해 주세요.', tone:'error'}, storageEpoch);
        return;
      }
      dispatch({type: 'cancel'});
      setDraft(sentDraft);
      const message = error instanceof FactCheckError && /CONFIG|KEY_MISSING/i.test(error.code) ? configurationHelp : error instanceof Error ? `검증 실패: ${error.message} 다시 시도하실 수 있습니다.` : '검증 요청에 실패했습니다. 네트워크를 확인하고 다시 시도해 주세요.';
      if (error instanceof FactCheckError && /CONFIG|KEY_MISSING/i.test(error.code)) setConfigured(false);
      setNotice(message);
      if (progressMessageId) {
        saveChat({role:'assistant',text:message,tone:'error'},storageEpoch);
        const errorId = `message-${messageCounter.current++}`;
        setMessages(messages => {
          const target = messages.find(item => item.id === progressMessageId);
          if (target?.progress) {
            return messages.map(item => item.id === progressMessageId ? {...item, progress: {...item.progress, error: message}} : item);
          }
          return [...messages.filter(item => item.id !== progressMessageId), {id: errorId, role: 'assistant', text: message, tone: 'error'}];
        });
      } else {
        appendReply({role: 'assistant', text: message, tone: 'error'});
      }
    } finally {
      if (generation.current === current) request.current = null;
    }
  }

  function restoredMessage(item:StoredMessage):ChatMessage {
    if(item.snapshot){const result=restoreSnapshot(item.snapshot);const jev=item.snapshot.scoreMode==='jev'||result.model==='jev-latest';return {id:item.id,role:item.role,...composeAssistantReply(result,jev?result:null),meta:`과거 검증 결과 · ${formatCheckedAt(result.checkedAt)}`};}
    return {id:item.id,role:item.role,text:item.content,...(item.status==='failed'?{tone:'error' as const}:{}),meta:item.status==='cancelled'?'중단된 요청':undefined};
  }

  function restorePage(page:MessagePage,earlier=false) {
    const restored=page.messages.map(restoredMessage);
    setMessages(current=>earlier?[...restored,...current.filter(item=>!restored.some(old=>old.id===item.id))]:restored.length?restored:[WELCOME_MESSAGE]);
    const last=[...page.messages].reverse().find(item=>item.snapshot)?.snapshot;
    if(last&&(!earlier||!liveResult)){const result=restoreSnapshot(last);setLiveResult(result);dispatch({type:'load',snapshot:result});setNotice(`과거 검증 결과입니다 (${formatCheckedAtInline(result.checkedAt)}). 현재 사실로 재검증한 결과가 아닙니다.`);}
    else if(!earlier){setLiveResult(null);dispatch({type:'reset'});setNotice('저장된 대화를 불러왔습니다. 저장을 켜면 이어지는 대화도 저장됩니다.');}
  }

  async function selectConversation(id:string) {
    stop();dispatch({type:'cancel'});const current=generation.current;
    setLiveResult(null);dispatch({type:'reset'});
    setMessages([WELCOME_MESSAGE]);setDraft('');setFocus('');setImage(null);setSample(false);
    const page=await storage.loadConversation(id);
    if(page&&generation.current===current)restorePage(page);
  }

  async function earlierConversation() {
    const current=generation.current;const page=await storage.loadEarlier();
    if(page&&generation.current===current)restorePage(page,true);
  }

  function deleteConversation(id:string) {
    if(storage.active===id)reset();else if(request.current)cancelVerification();else stop();
    void storage.deleteConversation(id);
  }

  function download() {
    if (!snapshot) return;
    const exportResult = liveResult ? {...liveResult, sources: stripYoutubeApiDataForExport(liveResult.sources)} : liveResult;
    const content = snapshot.demo ? {title: 'True or Not 합성 예시', disclaimer: '실제 검증 결과가 아닙니다.', ...snapshot, documents} : {title: 'True or Not 검증 결과', disclaimer: 'AI 검증에는 오류가 있을 수 있습니다. 원출처를 확인해 주세요.', ...exportResult};
    const blobUrl = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], {type: 'application/json;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = snapshot.demo ? 'true-or-not-demo.json' : 'true-or-not-result.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    setNotice(snapshot.demo ? '합성 예시 JSON 다운로드를 요청했습니다.' : '원문·출처·불확실성을 포함한 검증 JSON 다운로드를 요청했습니다.');
  }

  const select = (id: string) => dispatch({type: 'select', id});

  return <MotionConfig reducedMotion="user"><div className="app-shell" id="top">
    <FloatingLinesBackground />
    <a className="skip-link" href="#workspace-main">본문으로 건너뛰기</a>
    <aside className="sidebar">
      <a className="brand" href="#top" aria-label="True or Not 홈"><span className="brand-symbol"><img src="/true-or-not-logo-04.png" alt="" width={36} height={20}/></span><span><ScrambleText>True or Not</ScrambleText><small>팩트체크 에이전트</small></span></a>
      <p className="nav-caption">워크스페이스</p>
      <LineSidebar
        className="workspace-nav"
        ariaLabel="주요 메뉴"
        items={[
          {label: <ScrambleText>대화 시작</ScrambleText>, icon: <Icon name="plus"/>},
          {label: <ScrambleText>검증 대시보드</ScrambleText>, icon: <Icon name="grid"/>},
        ]}
        defaultActive={0}
        onItemClick={index => {
          if (index === 0) document.getElementById('top')?.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'start'});
          if (index === 1) document.getElementById('review')?.scrollIntoView({behavior: reduce ? 'auto' : 'smooth', block: 'start'});
        }}
      />
      <ConversationHistory storage={storage} onNew={reset} onSelect={id=>void selectConversation(id)} onDelete={deleteConversation}/>
      <div className="sidebar-bottom"><div className="local-status"><span/>{serviceLabel}</div><p className="sidebar-foot">TRUE OR NOT / EVIDENCE WORKSPACE</p></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><span className="mobile-brand"><img src="/true-or-not-logo-04.png" alt="" width={26} height={15}/>True or Not</span><strong></strong></div><div className="topbar-actions"><button className="text-button" aria-label="사용 가이드" onClick={() => setDialog('guide')}><Icon name="book"/><span>사용 가이드</span></button><span className="profile-mark" aria-label="로컬 워크스페이스">F</span></div></header>
      <main id="workspace-main" className="page-content">
        <section className="composer panel-host chat-hero" aria-labelledby="chat-heading">
          <details className="conversation-mobile"><summary>대화 기록</summary><ConversationHistory storage={storage} onNew={reset} onSelect={id=>void selectConversation(id)} onDelete={deleteConversation}/></details>
          <div className="chat-intro chat-intro--wordmark">
            <h1 id="chat-heading" className="sr-only">True or Not</h1>
            <TechText
              text="True or Not"
              fontSize={145}
              letterSpacing={-0.02}
              dashGap={3}
              specks={48}
              strokeWidth={1}
              speed={0.7}
              reveal="area"
            />
          </div>
          <div className="chat-thread-wrap">
          {storage.loading&&<p role="status">저장된 대화를 불러오고 있습니다.</p>}
          {storage.beforeSequence&&<button type="button" className="conversation-earlier" onClick={()=>void earlierConversation()}>이전 메시지 불러오기</button>}
          <div className={`chat-thread${scrolled ? ' is-scrolled' : ''}${atBottom ? ' is-at-bottom' : ''}`} ref={threadRef} onScroll={handleThreadScroll} aria-live="polite">
            {messages.map(message => <motion.div key={message.id} className={`chat-message ${message.role === 'user' ? 'is-user' : 'is-assistant'} ${message.answer ? 'has-answer' : ''} ${message.scoreMode === 'jev' ? 'has-fact-score' : ''} ${message.progress ? 'has-progress' : ''} ${message.tone === 'error' ? 'is-error' : ''}`} initial={reduce ? false : {opacity: 0, y: 10}} animate={{opacity: 1, y: 0}} transition={{duration: reduce ? 0 : .22}}>
              {message.role === 'assistant' && <span className="chat-avatar"><Icon name="lens" size={16}/></span>}
              <div className={`chat-bubble ${message.answer ? 'chat-bubble--answer' : ''} ${message.scoreMode === 'jev' ? 'chat-bubble--fact-score' : ''}`}>
                {message.answer ? (message.scoreMode === 'jev' && message.factScore !== undefined
                  ? <><JevFactScore score={message.factScore} verdict={message.verdict} search={message.search}/><JevSourceList sources={message.sources ?? []}/></>
                  : <>{message.factScore !== undefined && <JevFactScore score={message.factScore} verdict={message.verdict} engine={message.scoreEngine ?? '종합'}/>}<AnswerOverview answer={message.answer} sources={message.sources ?? []} messageId={message.id}/></>) : message.progress ? <ProgressReply progress={message.progress}/> : message.thinking ? <ThinkingLoader label={notice || '근거를 모으고 사실 여부를 대조하고 있습니다.'}/> : message.summary ? <SummaryReply summary={message.summary}/> : <>{message.imagePreview && <img className="chat-image-preview" src={message.imagePreview} alt="사용자가 보낸 이미지"/>}{message.text ? <p>{message.text}</p> : null}</>}
                {message.meta && <small>{message.meta}</small>}
              </div>
            </motion.div>)}
            {busy && !messages.some(message => message.thinking || (message.progress && !message.progress.completed && !message.progress.error)) && <div className="chat-message is-assistant chat-message--loading" data-testid="verification-loading"><span className="chat-avatar"><Icon name="lens" size={16}/></span><div className="chat-bubble"><div className="chat-loader-row"><LatticeLoader label="검증 중" doneLabel="검증 완료" errorLabel="검증 실패" pattern="orbit" grid={3} shape="round" cellSize={7} gap={3} fontSize={12} step={75} idleOpacity={0.15} glow color="#ffffff" showTimer/><span>{notice || '근거를 모으고 사실 여부를 대조하고 있습니다.'}</span></div></div></div>}
          </div>
          {!atBottom && <button type="button" className="thread-to-bottom" onClick={() => {stickToBottom.current = true; scrollThreadToBottom(); setAtBottom(true);}} aria-label="채팅 맨 아래로 이동"><Icon name="arrow" size={16}/></button>}
          </div>
          <form ref={form} className="chat-form" onSubmit={submit}>
            <BorderGlow className="chat-input-shell" borderRadius={19} backgroundColor="#1c1f23" glowIntensity={1.9} glowRadius={46} animated coneSpread={32}>
              <label className="sr-only" htmlFor="document-text">확인할 원문</label>
              <textarea ref={editor} id="document-text" value={draft} onChange={event => {setDraft(event.target.value); if (sample) {setSample(false); setMessages([WELCOME_MESSAGE]);}}} onPaste={async event => {
                const item = [...(event.clipboardData?.items ?? [])].find(entry => entry.type.startsWith('image/'));
                if (!item || busy) return;
                const file = item.getAsFile();
                if (!file) return;
                const attached = await downscaleImage(file);
                if (attached) attachImage(attached);
              }} placeholder="확인하고 싶은 주장이나 원문을 입력해 주세요. 이미지는 Ctrl+V로 붙여넣을 수 있습니다." rows={1} maxLength={12000} onKeyDown={event => {if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return; event.preventDefault(); event.currentTarget.form?.requestSubmit();}}/>
              <div className="chat-input-meta"><span>{draft.length.toLocaleString()} / 12,000</span><span>Shift+Enter로 줄바꾸기</span></div>
              {(image || detectedLink) && <div className="chat-attachments">
                {image && <span className="attach-chip"><img src={image.preview} alt="첨부 이미지 미리보기"/><button type="button" onClick={() => setImage(null)} aria-label="이미지 제거">×</button></span>}
                {detectedLink && <span className="attach-chip is-link"><Icon name="link" size={14}/><span>링크 인식됨</span></span>}
              </div>}
              <div className="chat-toolbar">
                <div className="chat-tools"><button type="button" className="chat-tool" onClick={() => fileInput.current?.click()} disabled={busy} aria-label="이미지 첨부"><Icon name="file" size={16}/><span>이미지</span></button><input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="이미지 첨부" tabIndex={-1} onChange={async event => {const file = event.target.files?.[0]; event.target.value = ''; if (!file || busy) return; const attached = await downscaleImage(file); if (attached) attachImage(attached);}}/><label className="chat-focus-control" htmlFor="focus-request"><Icon name="lens" size={15}/><span>확인 요청</span><input id="focus-request" value={focus} maxLength={500} onChange={event => setFocus(event.target.value)} placeholder="선택 입력"/></label></div>
                <div className="chat-send-group">
                  <span className="chat-jev-toggle"><BellToggle pressed={jevMode} onChange={setJevMode} disabled={busy || jevConfigured !== true || !!image} offLabel="JEV OFF" onLabel=" JEV ON" revealBounce={0.3} waves={false} badge={false} size="sm" label="JEV 모드"/></span>
                  <div className="chat-model-control"><span className="sr-only">답변 모델</span><GlideSelect options={modelPickerOptions} value={modelSelection} onChange={value => setModelSelection(value as ModelSelection)} disabled={busy} ariaLabel="답변 모델 선택" ariaDescribedBy="model-preference-help" size="sm" radius={9} menuWidth={260} placement="top" align="right"/></div>
                  <span id="model-preference-help" className="sr-only">Auto는 설정된 모델을 순서대로 시도합니다. 개별 모델은 단독 사용합니다. JEV 스위치를 켜면 TypeSafe 빠른 판정 점수도 함께 표시하며 이미지는 지원하지 않습니다.</span>
                  {busy
                    ? <button type="button" className="chat-send is-stop" onClick={cancelVerification} aria-label="검증 중단"><Icon name="close" size={19}/></button>
                    : <button type="submit" className="chat-send" disabled={!draft.trim() && !image} aria-label={sample ? '예시 다시 보기' : '팩트 검증 시작'}><Icon name="arrow" size={19}/></button>}
                </div>
              </div>
            </BorderGlow>
            <div className="chat-footer"><div>{sample && <span className="sample-state"><Icon name="shield" size={14}/>합성 예시는 외부로 전송하지 않습니다.</span>}<button type="button" className="sample-chip" onClick={() => externalConsent ? revokeExternalConsent() : openConsentDialog('external-consent')}>{externalConsent ? '외부 전송 동의 철회' : '외부 전송 안내'}</button></div><button type="button" className="sample-chip" onClick={loadSample}>예시로 시작하기 <Icon name="arrow" size={14}/></button></div>
          </form>
          {!storagePreferenceSaved && <p className="dialog-notice" role="alert">브라우저 저장이 차단되어 선택 변경은 현재 화면에서만 적용됩니다. 이전 저장 설정이 남아 있으면 새로고침 후 다시 적용될 수 있으므로 사이트 데이터 설정도 확인해 주세요.</p>}
          <div className={`chat-status ${busy ? 'is-busy' : ''}`} role="status" aria-live="polite">{busy ? notice || '검증을 진행하고 있습니다.' : notice || (configured === false && jevConfigured !== true ? configurationHelp : '원문을 입력하거나 예시로 시작해 근거를 확인해 보세요.')}</div>
        </section>

        <section id="review" className="review-section" aria-labelledby="review-heading">
          <div className="review-heading dashboard-heading"><div><span className="section-kicker">검증 대시보드</span><h2 id="review-heading"><ScrambleText>근거와 함께 확인하세요.</ScrambleText></h2><p>주장별 신뢰지수, 확인된 인용, 출처의 관계를 한 흐름으로 살펴보세요.</p></div><button className="secondary-button export-button" disabled={!snapshot || busy} onClick={download}><Icon name="download" size={16}/><span>{snapshot?.demo ? '예시 내보내기' : '결과 내보내기'}</span></button></div>
          {snapshot ? <>
            <div className="dashboard-meta"><span className="document-title"><Icon name={snapshot.demo ? 'book' : 'file'} size={16}/>{snapshot.demo ? '합성 예시 · 외부 전송 없음' : '직접 입력한 원문 · 실제 검증'}</span><div><span>{snapshot.claims.length}개 주장</span><span>{sourceCount}개 출처</span>{snapshot.demo ? <span>시연용 데이터</span> : liveResult?.checkedAt ? <time className="dashboard-checked-at" dateTime={liveResult.checkedAt}>{formatCheckedAt(liveResult.checkedAt)}</time> : <span>검증 시점 기록됨</span>}</div></div>
            {!snapshot.demo && liveResult?.market && <Panel className="market-panel"><div className="panel-top"><h3><Icon name="grid" size={17}/><ScrambleText>주가 맥락</ScrambleText></h3><span>참고용 · 판정 근거 아님</span></div><StockChart market={liveResult.market}/></Panel>}
            <>
            <div className={`dashboard-detail-layout mobile-${mobileTab}`}>
              <div className="dashboard-left-stack">
                <Panel className="trust-panel"><TrustIndex score={trustScore} claimCount={snapshot.claims.length} sourceCount={sourceCount} evidenceCount={evidenceCount} warningCount={warningCount} claims={snapshot.claims} selectedClaimId={selected?.id} onSelectClaim={select}/></Panel>
                <div className="mobile-tabs" role="group" aria-label="검토 화면 선택"><span className="mobile-tabs-indicator" data-active={mobileTab} aria-hidden="true"/><button aria-pressed={mobileTab === 'results'} onClick={() => setMobileTab('results')}>결과</button><button aria-pressed={mobileTab === 'sources'} onClick={() => setMobileTab('sources')}>출처</button></div>
                <Panel className="source-index-panel"><div className="panel-top"><h3><Icon name="book" size={17}/><ScrambleText>검토한 출처</ScrambleText></h3><span>{sourceCount}개 수집</span></div><div className="source-index-grid">{snapshot.demo ? documents.map((source, index) => <button className={selectedSourceIds.has(source.id) ? 'source-index-card is-selected-claim-source' : 'source-index-card'} ref={spotlight} key={source.id} onClick={() => setDialog(source.id)}><span className="source-index-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{source.title}</strong><small>{source.publisher}</small></span><Icon name="arrow" size={15}/></button>) : liveResult?.sources.map((source, index) => {const href = safeSourceUrl(source.url); const sourceLabel = source.sourceType === '유튜브' ? source.youtubeDataStatus === 'collected' ? `공개 댓글 ${source.youtubeComments.length}개` : source.youtubeDataStatus === 'not_configured' ? '댓글 API 미설정' : '댓글 조회 불가' : source.accessStatus === 'verified' ? '원문 확인' : '접근 불가'; const content = <><span className="source-index-number">{String(index + 1).padStart(2, '0')}</span><span><strong>{source.youtubeTitle || source.title}</strong><small>{source.sourceType} · {source.publisher} · {sourceDiscoveryLabel(source)} · {sourceLabel}</small></span><Icon name="arrow" size={15}/></>; return href ? <a className={selectedSourceIds.has(source.id) ? 'source-index-card is-selected-claim-source' : 'source-index-card'} ref={spotlight} href={href} target="_blank" rel="noopener noreferrer" key={source.id}>{content}</a> : <div className={selectedSourceIds.has(source.id) ? 'source-index-card is-selected-claim-source' : 'source-index-card'} ref={spotlight} key={source.id}>{content}</div>;})}{!sourceCount && <div className="source-index-empty">아직 수집된 출처가 없습니다.</div>}</div></Panel>
              </div>
              <Panel className="evidence-panel"><div className="panel-top"><h3 className="scramble-panel-title"><Icon name="lens" size={18}/><ScrambleText>선택한 주장과 근거</ScrambleText></h3><span>{snapshot.demo ? '예시 비교' : '수집된 원문 비교'}</span></div><AnimatePresence mode="wait" initial={false}><motion.div className="detail-content" key={selected?.id || 'empty'} initial={reduce ? false : {opacity: 0, y: 5}} animate={{opacity: 1, y: 0}} exit={{opacity: 0}} transition={{duration: reduce ? 0 : 0.18}}>{selected ? <>
                <div className="result-overview"><span className="article-kicker">선택한 주장</span><h3>{selected.quote}</h3><Badge claim={selected}/><p>{selected.summary}</p></div>
                {!snapshot.demo && selectedLiveClaim && <div className="detail-blocks"><div><h4><ScrambleText>확인된 내용</ScrambleText></h4>{selectedLiveClaim.confirmed.length ? <ul>{selectedLiveClaim.confirmed.map((text, index) => <li key={index}>{text}</li>)}</ul> : <p>직접 확인된 내용이 없습니다.</p>}</div><div><h4><ScrambleText>남은 불확실성</ScrambleText></h4>{selectedLiveClaim.unresolved.length ? <ul>{selectedLiveClaim.unresolved.map((text, index) => <li key={index}>{text}</li>)}</ul> : <p>현재 기록된 불확실성이 없습니다.</p>}</div>{selectedLiveClaim.warnings.length > 0 && <div><h4><ScrambleText>주장별 주의사항</ScrambleText></h4><ul>{selectedLiveClaim.warnings.map((text, index) => <li key={index}>{text}</li>)}</ul></div>}</div>}
              </> : <div className="empty-evidence"><Icon name="lens" size={27}/><h4><ScrambleText>주장을 선택해 주세요</ScrambleText></h4><p>위의 주장 카드를 선택하면 연결된 출처와 인용이 표시됩니다.</p></div>}</motion.div></AnimatePresence></Panel>
            </div></>
          </> : <Panel className="dashboard-empty"><div className="empty-orbit"><Icon name="lens" size={31}/></div><h3><ScrambleText>검증 결과가 이곳에 쌓입니다.</ScrambleText></h3><p>대화창에 원문을 보내면 주장별 신뢰지수와 근거 출처를 연결해 보여드립니다.</p><div className="empty-preview-stats"><span><strong>--</strong><small>신뢰지수</small></span><span><strong>--</strong><small>검토 출처</small></span><span><strong>--</strong><small>연결 근거</small></span></div><button className="secondary-button" onClick={loadSample}>예시 대시보드 보기 <Icon name="arrow"/></button></Panel>}
        </section>
        <footer className="page-footer"><span><span className="footer-mark">F</span>True or Not <span className="footer-divider">/</span>판단을 대신하지 않고, 근거를 연결합니다.</span><span className="footer-links"><button type="button" className="text-button" onClick={() => openConsentDialog('storage-consent')}>대화 저장 설정</button><a href="/privacy#conversation-storage" target="_blank" rel="noopener noreferrer">개인정보 처리방침</a><a href="/terms">이용약관</a><a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener noreferrer">YouTube 약관</a><a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google 개인정보</a></span><button className="text-button" onClick={() => setDialog('guide')}>검증 원칙<Icon name="arrow" size={15}/></button></footer>
      </main>
    </div>
    <Modal open={dialog !== null} title={dialog === 'external-consent' ? '외부 서비스 전송 동의' : dialog === 'storage-consent' ? '대화 저장 설정' : activeDocument?.title || (dialog === 'guide' ? '근거를 읽는 세 가지 원칙' : '검증 안내')} onClose={() => {pendingConsent.current = false; setDialog(null);}} footer={dialog === 'external-consent' ? <div className="dialog-done"><button type="button" className="secondary-button" onClick={() => {pendingConsent.current = false; setDialog(null);}}>동의하지 않음</button><button type="button" className="secondary-button" onClick={acceptExternalConsent}>동의하고 시작</button></div> : dialog === 'storage-consent' ? <div className="dialog-done"><button type="button" className="secondary-button" onClick={() => setDialog(null)}>취소</button><button type="button" className="secondary-button" onClick={() => {applyStorageConsent(); setDialog(null);}}>설정 저장</button></div> : undefined}>
      {dialog === 'external-consent' || dialog === 'storage-consent' ? <div className="about-copy">
        {dialog === 'external-consent' ? <>
        <p>의도 분석·검증·요약을 위해 입력한 텍스트, 확인 요청, 링크, 첨부 이미지와 필요한 이전 대화 맥락을 서버로 전송합니다. 설정된 AI 서비스(Experiential 게이트웨이를 통한 DeepSeek·OpenAI·Google Gemini·AI Gateway), TypeSafe JEV, 검색 서비스(Tavily 및 모델 제공자의 검색 기능)가 요청 처리에 사용될 수 있습니다. 링크와 검색된 공개 페이지는 서버에서 읽으며 YouTube 기능은 Google 서비스에 영상 ID를 전송해 자막·공개 영상 정보·댓글을 조회할 수 있습니다.</p>
        <p>민감정보·제3자의 비공개 정보는 입력하지 마세요. 외부 제공자의 처리·보관 정책은 <a href="/privacy" target="_blank" rel="noopener noreferrer">개인정보 처리방침</a>과 <a href="/terms" target="_blank" rel="noopener noreferrer">이용약관</a>에서 확인해 주세요. 이 안내는 법적 검토 완료를 의미하지 않습니다.</p>
        <p>전송 동의는 이 브라우저에서 안내 버전만 저장해 다음 질문과 새로고침 후에도 유지합니다. 동의 철회·사이트 데이터 삭제·안내 범위 변경 시 다시 확인하며, 브라우저 저장이 차단되면 현재 화면에서만 유지합니다. 거절하면 외부 호출을 하지 않고 입력을 보존합니다. 대화 저장은 별도 선택이며 자동으로 켜지지 않습니다.</p>
        </> : <p>대화 저장은 외부 전송 동의와 별개입니다. 저장을 꺼도 기존 기록은 남으며 대화 목록의 삭제 버튼으로 지울 수 있습니다.</p>}
        <label className="conversation-consent"><input type="checkbox" checked={storageConsentDraft} onChange={event => setStorageConsentDraft(event.target.checked)}/>이 브라우저에서 대화 저장 <span>(선택)</span></label>
        {!storagePreferenceSaved && <p role="status">브라우저 저장이 차단되어 선택 변경은 현재 화면에서만 적용됩니다. 이전 저장 설정이 남아 있으면 새로고침 후 다시 적용될 수 있으므로 사이트 데이터 설정도 확인해 주세요.</p>}
        <p>처음에는 꺼짐이며 확정한 이후의 메시지와 최종 검증 결과만 서버 DB에 저장합니다. 저장 선택은 이 브라우저에서 새로고침 후에도 유지하며 사이트 데이터 삭제·안내 버전 변경 시 다시 꺼집니다. 기존 기록은 익명 쿠키가 유효한 동안 복원할 수 있습니다. 자세한 저장 항목·쿠키 만료·삭제·무료 DB 보관 제한은 <a href="/privacy#conversation-storage" target="_blank" rel="noopener noreferrer">개인정보 처리방침의 대화 저장 안내</a>에서 확인할 수 있습니다. 이후에는 웹 하단의 ‘대화 저장 설정’에서 변경할 수 있습니다.</p>
      </div> : activeDocument ? <><p className="dialog-notice">합성 예시 문서 · 외부 출처 링크가 아닙니다.</p><dl className="document-metadata"><dt>작성 주체</dt><dd>{activeDocument.publisher}</dd><dt>설정 날짜</dt><dd>{activeDocument.date}</dd><dt>원자료 관계</dt><dd>그룹 {activeDocument.group} · {activeDocument.relation}</dd></dl><div className="document-fulltext">{activeDocument.text}</div></> : dialog === 'guide' ? <ol className="guide-list"><li><span>01</span><div><h3><ScrambleText>주장을 작게 나누세요.</ScrambleText></h3><p>누가, 언제, 어디서, 어떤 조건으로 한 말인지 원문과 함께 확인하세요.</p></div></li><li><span>02</span><div><h3><ScrambleText>출처의 수보다 관계를 보세요.</ScrambleText></h3><p>같은 발표를 옮긴 여러 문서는 하나의 원자료를 공유할 수 있습니다.</p></div></li><li><span>03</span><div><h3><ScrambleText>모르는 것은 남겨 두세요.</ScrambleText></h3><p>근거가 없다고 거짓은 아닙니다. 의견과 미래 예측을 확정된 사실처럼 판정하지 않습니다.</p></div></li></ol> : <div className="about-copy"><p>최초 전송 동의 후 원문과 확인 요청은 서버, 외부 AI 및 검색 서비스로 전송됩니다. 채팅에 붙인 링크의 페이지는 서버에서 직접 가져오고, 첨부한 이미지는 주장 추출을 위해 AI 제공자에게 보내며 대화 DB에는 저장하지 않습니다. YouTube 자막·영상 정보·공개 댓글을 조회할 수 있으며 댓글은 LLM 입력 및 판정 근거로 사용하지 않습니다.</p><p>대화 저장은 별도 선택입니다. 저장하지 않은 결과와 YouTube API 정보는 현재 화면 메모리에만 유지되며 새로고침하면 사라집니다. YouTube API 제목·댓글은 대화 저장과 JSON 내보내기에서 제외됩니다. 자세한 내용은 <a href="/privacy">개인정보 처리방침</a>과 <a href="/terms">이용약관</a>을 확인해 주세요.</p></div>}
    </Modal>
  </div></MotionConfig>;
}
