import type {
  CollectionDetail,
  CollectionInfo,
  ImportStageResult,
  ModelStatus,
  RefreshResult,
  SearchResponse,
  SessionInfo,
} from './types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  let payload: any = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.error || `请求失败（HTTP ${response.status}）`);
  }
  return payload as T;
}

export const api = {
  health: () => request<{ ok: boolean; db: any; model: any }>('/health'),
  modelStatus: () => request<ModelStatus>('/model/status'),

  listCollections: () => request<{ collections: CollectionInfo[] }>('/collections'),
  createCollection: (name: string) =>
    request<{ collection: CollectionInfo }>('/collections', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  deleteCollection: (id: string) =>
    request<{ ok: boolean }>(`/collections/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  getCollection: (id: string) =>
    request<CollectionDetail>(`/collections/${encodeURIComponent(id)}`),

  importDocument: (
    id: string,
    payload: {
      title: string;
      content: string;
      contentHash?: string;
      chunks: { text: string; embedding: number[] }[];
      deferRefresh?: boolean;
    },
  ) =>
    request<{ staged: ImportStageResult; refresh: RefreshResult | null }>(
      `/collections/${encodeURIComponent(id)}/import`,
      { method: 'POST', body: JSON.stringify(payload) },
    ),
  refresh: (id: string) =>
    request<{ refresh: RefreshResult }>(`/collections/${encodeURIComponent(id)}/refresh`, {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  deleteDocument: (id: string, docId: string) =>
    request<{ removed: { docId: string; deletedChunks: number }; refresh: RefreshResult }>(
      `/collections/${encodeURIComponent(id)}/documents/${encodeURIComponent(docId)}`,
      { method: 'DELETE' },
    ),

  search: (
    id: string,
    payload: { query: string; embedding: number[]; topK?: number; sessionId?: string },
  ) =>
    request<SearchResponse>(`/collections/${encodeURIComponent(id)}/search`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getSession: (sessionId: string) =>
    request<{ session: SessionInfo | null }>(`/sessions/${encodeURIComponent(sessionId)}`),
  patchSession: (
    sessionId: string,
    payload: { collectionId?: string; backend?: string; dtype?: string; lastQuery?: string },
  ) =>
    request<{ session: SessionInfo }>(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
};
