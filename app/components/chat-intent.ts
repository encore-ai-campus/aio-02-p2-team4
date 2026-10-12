import type { AttachedImage, FactCheckAnswer, FactCheckResult } from '../lib/fact-check-contract';
import type { GateDecision } from '../lib/chat-intent-contract';
export type { GateDecision } from '../lib/chat-intent-contract';

export type ChatIntent =
  | {kind: 'meta'; topic: 'history' | 'greeting' | 'thanks' | 'identity' | 'control' | 'tease' | 'smalltalk' | 'help'}
  | {kind: 'verify'}
  | {kind: 'clarify'};

type MetaTopic = 'history' | 'greeting' | 'thanks' | 'identity' | 'control' | 'tease' | 'smalltalk' | 'help';

// Unambiguous verification signals: hearsay, truth and evidence vocabulary.
// A bare question mark is not enough ("밥 먹었어?" must stay small talk).
const CLAIM_PATTERNS = [
  /인지/, /사실/, /진실/, /거짓/, /진짜/, /정말/,
  /맞는지/, /맞아/, /맞니/, /틀린지/, /틀렸/, /틀리니/,
  /확인/, /검증/, /주장/, /근거/, /출처/, /카더라/, /라던데/, /라는데/,
];
const EXPLICIT_VERIFY_PATTERNS = [
  /사실인지/, /사실 여부/, /진짜인지/, /정말 사실/, /맞는지/, /틀린지/, /거짓인지/, /팩트\s*체크/,
];
const FOLLOW_UP_REFERENCES = /기억해|그거|그것|이전|아까|방금|앞서|위에/;
const SHIELD_GUARD = /하지 ?마|그만해|닥쳐|조용히/;

const IDENTITY_PATTERNS = [/너는 누구/, /너가 누구/, /너는 뭐야/, /너가 뭐야/, /자기소개/, /뭐하는/, /누구야$/, /무슨 ?모델/, /어떤 모델/, /모델명/];

const EARLY_META: Array<{topic: MetaTopic; patterns: RegExp[]}> = [
  {topic: 'history', patterns: [/볼\s*수\s*있/, /보여줘/, /기억/, /대화/, /지금까지/, /여태까지/, /뭘 검증했/, /뭐 검증했/, /검증 기록/, /검증한 거/, /무슨 검증/, /대화 기록/, /채팅 기록/]},
  {topic: 'greeting', patterns: [/^안녕/, /^하이/, /^헬로/, /^반가워/, /^안녕하세요/, /^ㅎㅇ[!?.\s]*$/]},
  {topic: 'thanks', patterns: [/고마워/, /감사/, /고생했/, /땡큐/, /수고했/]},
  {topic: 'identity', patterns: IDENTITY_PATTERNS},
];

const HELP_PATTERNS = [/뭘 할 수 있/, /뭐 할 수 있/, /뭐할 수 있/, /도와줘/, /도울 수 있/, /기능이 뭐/, /기능 뭐/, /사용법/, /어떻게 써/, /어떻게 사용/];

const LATE_META: Array<{topic: MetaTopic; patterns: RegExp[]}> = [
  {topic: 'control', patterns: [/존댓말/, /반말/, /높임말/, /말투/, /해라체/, /하게체/, /합쇼체/, /하오체/, /실시$/]},
  {topic: 'tease', patterns: [/야임마/, /야이/, /^개새(?:끼|야)?[!?.\s]*$/, /(^|[\s!?.])야([\s!?.]|$)/, /어이/, /이봐/, /바보/, /멍청/, /또라이/, /미친/, /못생겼/, /못생긴/, /하지마/, /하지 마/, /그만해/, /닥쳐/, /조용히/]},
  {topic: 'smalltalk', patterns: [/뭐해/, /뭐하냐/, /뭐하니/, /뭐하고 있/, /심심/, /놀자/, /놀아줘/, /잘자/, /잘 자/, /밥 먹었/, /밥먹었/]},
];

// Summarize requests ("요약해줘") bypass verification: the user wants a
// research summary of linked or pasted content, not a truth judgment.
const SUMMARIZE_PATTERNS = [/요약/, /서머리/, /summar/i];

export function isSummarizeRequest(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed || !SUMMARIZE_PATTERNS.some(pattern => pattern.test(trimmed))) return false;
  return !CLAIM_PATTERNS.some(pattern => pattern.test(trimmed));
}

export function isIdentityQuestion(text: string): boolean {
  const trimmed = text.trim();
  return trimmed.length > 0 && trimmed.length <= 60 && IDENTITY_PATTERNS.some(pattern => pattern.test(trimmed));
}

export function classifyChatInput(
  text: string,
  options: {hasAttachment: boolean; providerAuthFailed?: boolean},
): ChatIntent {
  const trimmed = text.trim();
  if (!trimmed) return {kind: 'clarify'};
  if (!options.hasAttachment && trimmed.length <= 60) {
    for (const group of EARLY_META) {
      if (group.patterns.some(pattern => pattern.test(trimmed))) return {kind: 'meta', topic: group.topic};
    }
    if (HELP_PATTERNS.some(pattern => pattern.test(trimmed))) return {kind: 'meta', topic: 'help'};
  }
  if (!options.providerAuthFailed && EXPLICIT_VERIFY_PATTERNS.some(pattern => pattern.test(trimmed)) && !FOLLOW_UP_REFERENCES.test(trimmed)) return {kind: 'verify'};
  if (options.hasAttachment || trimmed.length > 60) return {kind: 'clarify'};
  if (!SHIELD_GUARD.test(trimmed) && CLAIM_PATTERNS.some(pattern => pattern.test(trimmed))) return {kind: 'clarify'};
  for (const group of LATE_META) {
    if (group.patterns.some(pattern => pattern.test(trimmed))) return {kind: 'meta', topic: group.topic};
  }
  return {kind: 'clarify'};
}

type ContextMessage = {role: string; text?: string; answer?: FactCheckAnswer; summary?: {summary: string}; thinking?: boolean; progress?: unknown};
type Material = {text: string; focus: string; image: AttachedImage | null; linkUrl: string | null};
export function clarificationMaterial<T extends Material>(decision: Pick<GateDecision, 'action' | 'target'>, current: T, previous: T | null): T | null {
  if (decision.action !== 'clarify') return null;
  return decision.target === 'previous' ? previous : current;
}
export function buildGateContext(messages: ContextMessage[], result: FactCheckResult | null) {
  return {
    previousText: result?.text.slice(0, 2000) ?? null,
    previousClaims: result?.claims.slice(0, 3).map(claim => ({quote: claim.quote.slice(0, 200), verdict: claim.verdict, score: claim.factScore})) ?? [],
    recentUser: messages.filter(message => message.role === 'user' && message.text).slice(-3).map(message => message.text!.slice(0, 200)),
    recentAssistant: messages.filter(message => message.role === 'assistant' && !message.thinking && !message.progress)
      .map(message => message.text || message.answer?.overview?.text || message.answer?.conclusion?.text || message.summary?.summary || '')
      .filter(Boolean).slice(-2).map(text => text.slice(0, 1500)),
    previousSources: result?.sources.slice(0, 6).map(({url, title, accessStatus}) => ({url, title, accessStatus})) ?? [],
    previousWarnings: result?.warnings.slice(0, 8).map(warning => warning.slice(0, 200)) ?? [],
  };
}

export function verificationInput(
  decision: GateDecision,
  input: {text: string; focus: string; image: AttachedImage | null; linkUrl: string | null},
  previousText: string | null,
  previousAttachment?: {focus?: string; image: AttachedImage | null; linkUrl: string | null},
) {
  if (decision.action !== 'verify') return null;
  const followUp = decision.target === 'previous';
  if (followUp && !previousText?.trim() && !previousAttachment?.image && !previousAttachment?.linkUrl) return null;
  const parts = [...(followUp ? [previousAttachment?.focus?.trim()] : []), input.focus.trim(), decision.focus?.trim(), ...(followUp ? [input.text.trim()] : [])].filter(Boolean);
  return {
    text: followUp ? previousText ?? '' : input.text,
    focus: [...new Set(parts)].join(' / ').slice(0, 500),
    image: followUp ? previousAttachment?.image ?? null : input.image,
    linkUrl: followUp ? previousAttachment?.linkUrl ?? null : input.linkUrl,
    followUp,
  };
}

export function describeHistory(
  messages: Array<{role: string; text?: string}>,
  result: FactCheckResult | null,
  demoText = '',
): string {
  const past = messages
    .filter(message => message.role === 'user' && message.text && message.text.trim() && message.text.trim() !== demoText.trim())
    .map(message => message.text!.trim().slice(0, 40));
  if (!past.length && !result) return '아직 검증한 기록이 없습니다. 확인할 원문·링크·이미지를 보내주시면 시작하겠습니다.';
  const lines = [`이 대화는 모두 표시됩니다. 지금까지 ${past.length}번 검증 요청이 있었습니다.`];
  for (const item of past.slice(-3)) lines.push(`· "${item}"`);
  if (result && result.claims.length) {
    const verdicts = result.claims.map(claim => `"${claim.quote.slice(0, 30)}" ${claim.verdict}(${claim.factScore}점)`);
    lines.push(`마지막 검증: 주장 ${result.claims.length}개 — ${verdicts.join(' / ')}`);
  }
  return lines.join('\n');
}

export function metaReply(topic: MetaTopic): string {
  if (topic === 'greeting') return '안녕하세요. 확인할 주장·원문·링크·이미지를 보내주시면 근거와 함께 검토하겠습니다.';
  if (topic === 'thanks') return '별말씀을요. 또 확인할 내용이 있으시면 보내주세요.';
  if (topic === 'control') return '그 기능은 아직 지원하지 않습니다. 확인할 주장·원문·링크·이미지를 보내주시면 검증하겠습니다.';
  if (topic === 'tease') return '확인할 내용이 있으시면 보내주세요. 근거를 바탕으로 정확히 따져보겠습니다.';
  if (topic === 'smalltalk') return '검증 대기 중입니다. 확인할 내용을 보내주시면 바로 시작하겠습니다.';
  if (topic === 'help') return '원문·링크·이미지를 주시면 주장을 나누고 출처 원문과 대조해 드립니다. 짧게 이어서 물어보시면 이전 검증을 바탕으로 찾아드립니다.';
  return 'True or Not은 원문 속 주장을 나누고 출처 원문과 대조해서 보여주는 팩트체크 에이전트입니다. 검증은 원문·링크·이미지를 보내시면 시작합니다.';
}
