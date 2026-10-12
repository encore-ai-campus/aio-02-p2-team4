// @ts-ignore -- explicit extension is required by the Node 24 native test runner.
import { scoreBand, scoreLabel } from '../lib/fact-score.ts';
import type { FactScoreBand } from '../lib/fact-score';

export type Claim = Readonly<{ id: string; quote: string; statement?: string; start: number; end: number; factScore: number; scoreBand: FactScoreBand; scoreLabel: string; verdict: string | null; tone: string; summary: string; evidenceIds: readonly string[] }>;
export type Preview = Readonly<{ text: string; focus: string; demo: boolean; claims: readonly Claim[] }>;
export type State = { snapshot: Preview | null; selectedId: string | null; status: 'idle' | 'loading' | 'ready' | 'cancelled'; token: number };
export type Action = {type: 'load'; snapshot: Preview} | {type: 'select'; id: string} | {type: 'start'} | {type: 'complete'; token: number; snapshot: Preview} | {type: 'cancel'} | {type: 'reset'};
export const initialState: State = {snapshot: null, selectedId: null, status: 'idle', token: 0};
export function transition(state: State, action: Action): State {
  if (action.type === 'start') return {...state, status: 'loading', token: state.token + 1};
  if (action.type === 'cancel') return {...state, status: 'cancelled', token: state.token + 1};
  if (action.type === 'reset') return {...initialState, token: state.token + 1};
  if (action.type === 'complete') return state.status === 'loading' && action.token === state.token ? transition(state, {type: 'load', snapshot: action.snapshot}) : state;
  if (action.type === 'load') return {...state, snapshot: action.snapshot, selectedId: action.snapshot.claims[0]?.id ?? null, status: 'ready'};
  if (action.type === 'select' && state.snapshot?.claims.some(c => c.id === action.id)) return {...state, selectedId: action.id};
  return state;
}
export function createPreview(draft: { text: string; focus: string }): Preview {
  const claims = Array.from(draft.text.matchAll(/[^.!?\n]+[.!?]?/g)).filter(m => m[0].trim()).slice(0, 3).map((m, i) => {
    const quote = m[0].trim();
    const start = m.index! + m[0].indexOf(quote);
    const factScore = 50;
    return Object.freeze({ id: `claim-${i + 1}`, quote, start, end: start + quote.length, factScore, scoreBand: scoreBand(factScore), scoreLabel: scoreLabel(factScore), verdict: null, tone: 'neutral', summary: '문장 단위로 나눈 후보입니다. 사실 여부와 문장 유형은 분석하지 않았습니다.', evidenceIds: Object.freeze([] as string[]) });
  });
  return Object.freeze({ text: draft.text, focus: draft.focus, demo: false, claims: Object.freeze(claims) });
}
