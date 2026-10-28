import type { Chunk } from './types';

export interface ChunkOptions {
  target?: number;
  overlap?: number;
}

interface Span {
  start: number;
  end: number;
}

export function normalizeText(input: string): string {
  return input
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

const SENTENCE_BREAK = /[。！？!?；;]+[”’」』】）)]*\s*|\n+/gu;

function sentenceSpans(text: string): Span[] {
  const spans: Span[] = [];
  let cursor = 0;
  for (const match of text.matchAll(SENTENCE_BREAK)) {
    const end = (match.index ?? 0) + match[0].length;
    if (end > cursor) spans.push({ start: cursor, end });
    cursor = end;
  }
  if (cursor < text.length) spans.push({ start: cursor, end: text.length });
  return spans;
}

function trimSpan(text: string, span: Span): Span {
  let { start, end } = span;
  while (start < end && /\s/u.test(text[start])) start += 1;
  while (end > start && /\s/u.test(text[end - 1])) end -= 1;
  return { start, end };
}

function splitLongSpan(span: Span, target: number, overlap: number): Span[] {
  const parts: Span[] = [];
  let start = span.start;
  while (start < span.end) {
    const end = Math.min(start + target, span.end);
    parts.push({ start, end });
    if (end >= span.end) break;
    start = Math.max(start + 1, end - overlap);
  }
  return parts;
}

export function chunkDocument(content: string, options: ChunkOptions = {}): Chunk[] {
  const text = normalizeText(content);
  const target = Math.max(80, options.target ?? 300);
  const overlap = Math.max(0, Math.min(options.overlap ?? 60, Math.floor(target / 2)));

  const spans = sentenceSpans(text);
  const pieces: Span[] = [];
  for (const span of spans) {
    if (span.end - span.start <= target) pieces.push(span);
    else pieces.push(...splitLongSpan(span, target, overlap));
  }

  const chunks: Chunk[] = [];
  let index = 0;
  let i = 0;
  while (i < pieces.length) {
    let start = pieces[i].start;
    let end = pieces[i].end;
    let j = i + 1;
    while (j < pieces.length && pieces[j].end - start <= target) {
      end = pieces[j].end;
      j += 1;
    }
    const trimmed = trimSpan(text, { start, end });
    if (trimmed.end > trimmed.start) {
      const body = text.slice(trimmed.start, trimmed.end);
      if (body.length >= 8) {
        chunks.push({ index: index++, text: body, start: trimmed.start, end: trimmed.end });
      }
    }
    if (j >= pieces.length) break;
    let next = j;
    while (next < pieces.length && pieces[next].end <= end - overlap) next += 1;
    i = Math.max(next, i + 1);
  }

  if (chunks.length >= 2) {
    const last = chunks[chunks.length - 1];
    const previous = chunks[chunks.length - 2];
    if (last.text.length < 40 && last.end - previous.start <= target * 1.4) {
      previous.end = last.end;
      previous.text = text.slice(previous.start, previous.end);
      chunks.pop();
    }
  }

  return chunks.map((chunk, position) => ({ ...chunk, index: position }));
}

export function embedInput(title: string, body: string): string {
  return `${title.trim()}\n${body}`;
}

export function chunkCountLabel(count: number): string {
  return count === 1 ? '1 个分块' : `${count} 个分块`;
}
