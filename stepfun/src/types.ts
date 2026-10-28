export type BackendName = 'webgpu' | 'wasm';
export type Dtype = 'fp32' | 'fp16' | 'q8';

export interface BackendCandidate {
  device: BackendName;
  dtype: Dtype;
}

export interface BackendStatus {
  backend: BackendName;
  dtype: Dtype;
  label: string;
  reason: string;
  webgpuDetected: boolean;
  forcedWasm: boolean;
  attempts: { candidate: string; ok: boolean; error?: string }[];
  loadMs?: number;
  warmupMs?: number;
}

export interface CollectionInfo {
  id: string;
  name: string;
  seekdbCollection: string;
  model: string;
  dimension: number;
  createdAt: number;
  updatedAt: number;
  docCount: number;
  chunkCount: number;
  lastRefreshAt: number;
  verified: number;
}

export interface DocumentInfo {
  docId: string;
  title: string;
  contentHash: string;
  charCount: number;
  chunkCount: number;
  importedAt: number;
}

export interface IndexStateInfo {
  docCount: number;
  chunkCount: number;
  lastImportAt: number;
  lastRefreshAt: number;
  refreshMs: number;
  verified: number;
}

export interface CollectionDetail {
  collection: Omit<CollectionInfo, 'docCount' | 'chunkCount' | 'lastRefreshAt' | 'verified'>;
  documents: DocumentInfo[];
  indexState: IndexStateInfo | null;
}

export interface Chunk {
  index: number;
  text: string;
  start: number;
  end: number;
}

export interface ImportStageResult {
  docId: string;
  title: string;
  chunkCount: number;
  removedChunks: number;
  timings: { addMs: number; cleanupMs: number; totalMs: number };
}

export interface Verification {
  docId: string;
  title: string;
  fulltextHit: boolean;
  fulltextProbe: string;
  vectorHit: boolean;
  vectorDistance: number | null;
  probeAvailable: boolean;
}

export interface RefreshResult {
  refreshMs: number;
  verified: boolean;
  docCount: number;
  chunkCount: number;
  storedChunks: number;
  countsMatch: boolean;
  verification: Verification | null;
}

export interface SearchHit {
  chunkId: string;
  docId: string;
  title: string;
  chunkIndex: number;
  text: string;
  distance: number | null;
}

export interface SearchResponse {
  results: SearchHit[];
  searchMs: number;
  candidateK: number;
  sanitizedQuery: string;
  topK: number;
  engine: string;
  fusion: string;
}

export interface ModelStatus {
  model: { id: string; upstream: string; onnxRepo: string; revision: string; dimension: number };
  dir: string;
  ready: boolean;
  files: Record<string, number | null>;
}

export interface SessionInfo {
  sessionId: string;
  collectionId: string | null;
  backend: string | null;
  dtype: string | null;
  lastQuery: string | null;
  updatedAt: number;
}

export interface SampleDoc {
  title: string;
  content: string;
  tags?: string[];
}

export interface SampleQuery {
  query: string;
  relevant: string[];
}
