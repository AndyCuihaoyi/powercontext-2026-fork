const QUERY_CHARS = /[^\p{L}\p{N}]+/gu;

export function sanitizeQuery(text, maxLength = 120) {
  const cleaned = String(text || '')
    .normalize('NFKC')
    .replace(QUERY_CHARS, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned.slice(0, maxLength).trim();
}

export function probeSnippet(text, length = 24) {
  const compact = String(text || '').replace(/\s+/g, '');
  if (!compact) return '';
  const start = Math.max(0, Math.floor((compact.length - length) / 2));
  return sanitizeQuery(compact.slice(start, start + length), length);
}
