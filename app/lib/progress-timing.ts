export type ProgressTiming = {
  requestStartedAt?: number;
  statusElapsedSeconds?: number;
  completed?: boolean;
  error?: string;
};

export function elapsedSecondsSince(startedAt: number, now: number): number {
  return Math.max(0, Math.floor((now - startedAt) / 100) / 10);
}

export function progressElapsedSeconds(progress: ProgressTiming, now: number): number {
  const current = progress.requestStartedAt === undefined ? 0 : elapsedSecondsSince(progress.requestStartedAt, now);
  if (progress.completed || progress.error) return progress.statusElapsedSeconds ?? current;
  return Math.max(progress.statusElapsedSeconds ?? 0, current);
}
