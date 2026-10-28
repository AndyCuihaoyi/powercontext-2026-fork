import { pipeline, type FeatureExtractionPipelineType } from '@huggingface/transformers';
import type { BackendCandidate, BackendStatus } from '../types';
import {
  MODEL_ID,
  candidateChain,
  configureLocalEnv,
  describeCandidate,
  detectWebGpu,
  statusFrom,
} from './backend';

export interface LoadProgress {
  stage: string;
  file?: string;
  progress?: number;
  loaded?: number;
  total?: number;
}

export interface EmbedderOptions {
  force?: BackendCandidate;
  warmup?: boolean;
  onLoadProgress?: (event: LoadProgress) => void;
  onAttempt?: (candidate: BackendCandidate, ok: boolean, error?: string) => void;
}

export class Embedder {
  readonly status: BackendStatus;
  private readonly extractor: FeatureExtractionPipelineType;
  private disposed = false;

  private constructor(extractor: FeatureExtractionPipelineType, status: BackendStatus) {
    this.extractor = extractor;
    this.status = status;
  }

  static async create(options: EmbedderOptions = {}): Promise<Embedder> {
    configureLocalEnv();
    const webgpu = await detectWebGpu();
    const chain = options.force
      ? [options.force]
      : candidateChain(webgpu);
    const attempts: BackendStatus['attempts'] = [];
    let lastError: Error | null = null;

    for (const candidate of chain) {
      const loadStarted = performance.now();
      try {
        const extractor = await pipeline('feature-extraction', MODEL_ID, {
          device: candidate.device,
          dtype: candidate.dtype,
          local_files_only: true,
          progress_callback: (event: any) => {
            options.onLoadProgress?.({
              stage: event?.status ?? 'progress',
              file: event?.file,
              progress: typeof event?.progress === 'number' ? event.progress : undefined,
              loaded: event?.loaded,
              total: event?.total,
            });
          },
        } as any);
        const loadMs = performance.now() - loadStarted;
        let warmupMs = 0;
        if (options.warmup !== false) {
          const warmStarted = performance.now();
          try {
            await extractor(['预热：本地向量化'], { pooling: 'cls', normalize: true } as any);
          } finally {
            warmupMs = performance.now() - warmStarted;
          }
        }
        attempts.push({ candidate: describeCandidate(candidate), ok: true });
        options.onAttempt?.(candidate, true);
        return new Embedder(extractor, statusFrom(candidate, webgpu, attempts, loadMs, warmupMs));
      } catch (error) {
        lastError = error as Error;
        const message = lastError.message || String(error);
        attempts.push({ candidate: describeCandidate(candidate), ok: false, error: message });
        options.onAttempt?.(candidate, false, message);
      }
    }

    throw new Error(
      `本地模型加载失败：${lastError?.message ?? '未知错误'}。请确认 public/models 与 public/ort 已就绪（npm run models:fetch / npm run build）。`,
    );
  }

  get ready(): boolean {
    return !this.disposed;
  }

  async embed(texts: string[], options: { batchSize?: number; onProgress?: (done: number, total: number) => void } = {}): Promise<number[][]> {
    if (this.disposed) throw new Error('Embedder 已释放');
    const batchSize = Math.max(1, Math.min(options.batchSize ?? 8, 32));
    const vectors: number[][] = [];
    for (let start = 0; start < texts.length; start += batchSize) {
      const batch = texts.slice(start, start + batchSize);
      const tensor = await this.extractor(batch, { pooling: 'cls', normalize: true } as any);
      const rows = tensor.tolist() as number[][];
      tensor.dispose?.();
      vectors.push(...rows);
      options.onProgress?.(Math.min(texts.length, start + batch.length), texts.length);
    }
    return vectors;
  }

  async embedOne(text: string): Promise<number[]> {
    const [vector] = await this.embed([text], { batchSize: 1 });
    return vector;
  }

  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    await Promise.resolve((this.extractor as any).dispose?.()).catch(() => {});
  }
}
