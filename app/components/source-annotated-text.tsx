import type { ReactNode } from 'react';
import { safeSourceUrl } from './fact-check-client';
import { CITATION_PATTERN, findMatchingSource } from '../lib/source-annotation';
import type { MinimalSource } from '../lib/source-annotation';

export type { MinimalSource };

export interface SourceAnnotatedTextProps {
  text: string;
  sources?: MinimalSource[];
  className?: string;
}

export default function SourceAnnotatedText({
  text,
  sources,
  className,
}: SourceAnnotatedTextProps) {
  if (!text) return null;

  const elements: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  CITATION_PATTERN.lastIndex = 0;

  while ((match = CITATION_PATTERN.exec(text)) !== null) {
    const matchStart = match.index;
    const matchEnd = match.index + match[0].length;
    const numStr = match[1] || match[2];

    if (matchStart > lastIndex) {
      elements.push(text.slice(lastIndex, matchStart));
    }

    const { source, displayNumber } = findMatchingSource(sources, numStr);
    const href = source?.url ? safeSourceUrl(source.url) : null;
    const tooltip = source
      ? `${source.title}${source.publisher ? ` · ${source.publisher}` : ''}`
      : `출처 [${displayNumber}]`;

    const key = `cite-${matchStart}-${numStr}`;

    if (href) {
      elements.push(
        <a
          key={key}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-citation"
          title={tooltip}
          aria-label={`출처 [${displayNumber}]: ${tooltip}. 새 탭에서 열기`}
        >
          [{displayNumber}]
        </a>,
      );
    } else {
      elements.push(
        <span
          key={key}
          className="inline-citation is-text"
          title={tooltip}
          aria-label={`출처 [${displayNumber}]: ${tooltip}`}
        >
          [{displayNumber}]
        </span>,
      );
    }

    lastIndex = matchEnd;
  }

  if (lastIndex < text.length) {
    elements.push(text.slice(lastIndex));
  }

  if (className) {
    return <span className={className}>{elements}</span>;
  }

  return <>{elements}</>;
}
