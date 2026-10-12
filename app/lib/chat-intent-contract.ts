export type GateDecision = {
  action: 'verify' | 'reply' | 'clarify';
  target: 'current' | 'previous';
  reply: string | null;
  focus: string | null;
  readLink?: boolean;
};

export function readGateDecision(value: unknown): GateDecision {
  if (!value || typeof value !== 'object') throw Error('INTENT_FAILED');
  const item = value as Partial<GateDecision>;
  const target = item.target ?? 'current';
  if (!['verify', 'reply', 'clarify'].includes(item.action ?? '') || !['current', 'previous'].includes(target)) throw Error('INTENT_FAILED');
  if (item.reply != null && (typeof item.reply !== 'string' || item.reply.length > 1500)) throw Error('INTENT_FAILED');
  if (item.focus != null && (typeof item.focus !== 'string' || item.focus.length > 500)) throw Error('INTENT_FAILED');
  if (item.readLink != null && typeof item.readLink !== 'boolean') throw Error('INTENT_FAILED');
  const reply = item.reply?.trim() || null;
  if (item.action !== 'verify' && !reply) throw Error('INTENT_FAILED');
  return {action: item.action as GateDecision['action'], target, reply, focus: item.focus?.trim() || null, ...(item.readLink ? {readLink: true} : {})};
}
