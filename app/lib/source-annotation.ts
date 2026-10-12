export const CITATION_PATTERN = /(?:\[[sS]?(\d+)\]|\b[sS](\d+)\b)/g;

export interface MinimalSource {
  id: string;
  title: string;
  url?: string;
  publisher?: string;
}

export function findMatchingSource(
  sources: MinimalSource[] | undefined,
  numStr: string,
): {
  source: MinimalSource | undefined;
  displayNumber: number;
} {
  const num = parseInt(numStr, 10);
  if (!sources || sources.length === 0 || isNaN(num)) {
    return { source: undefined, displayNumber: isNaN(num) ? 1 : num };
  }

  // 1. Match by source.id (e.g., 's1', 's2' or '1', '2')
  const targetId = `s${numStr}`.toLowerCase();
  let found = sources.find(
    s => s.id?.toLowerCase() === targetId || s.id?.toLowerCase() === numStr.toLowerCase(),
  );

  // 2. Fallback to 1-based array index
  if (!found && num >= 1 && num <= sources.length) {
    found = sources[num - 1];
  }

  const index = found ? sources.indexOf(found) : -1;
  const displayNumber = index >= 0 ? index + 1 : num;

  return { source: found, displayNumber };
}
