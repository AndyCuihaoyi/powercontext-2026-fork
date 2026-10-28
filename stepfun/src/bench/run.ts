import { api } from '../api';
import { chunkDocument, embedInput, normalizeText } from '../chunker';
import { Embedder } from '../embedding/embedder';
import { detectWebGpu } from '../embedding/backend';
import type { BackendCandidate, SampleDoc, SampleQuery } from '../types';

export interface VariantSpec extends BackendCandidate {
  key: string;
  label: string;
}

export interface BenchProgress {
  variant: string;
  stage: string;
  detail?: string;
  progress?: number;
}

export interface QualityMetrics {
  recall5: number;
  recall10: number;
  mrr: number;
  ndcg10: number;
  evaluatedQueries: number;
  hitQueries: number;
}

export interface LatencyStats {
  median: number;
  p95: number;
  min: number;
  max: number;
}

export interface BenchmarkVariantResult {
  key: string;
  label: string;
  device: string;
  dtype: string;
  status: 'ok' | 'error';
  error?: string;
  modelBytes: number | null;
  compressionRatio: number | null;
  loadMs: number | null;
  warmupMs: number | null;
  docCount: number;
  chunkCount: number;
  embedDocsMs: number | null;
  embedPerChunkMs: number | null;
  stageImportMs: number | null;
  refreshMs: number | null;
  refreshVerified: boolean | null;
  seedMs: number | null;
  firstQueryE2eMs: number | null;
  queryEmbedMs: LatencyStats | null;
  searchMs: LatencyStats | null;
  e2eMs: LatencyStats | null;
  quality: QualityMetrics | null;
}

export interface BenchmarkResult {
  schemaVersion: 1;
  startedAt: string;
  finishedAt: string;
  userAgent: string;
  webgpu: { available: boolean; reason: string };
  corpus: { docs: number; queries: number; chunksPerVariant: number | null };
  modelFiles: Record<string, number | null>;
  modelBytes: Record<string, number>;
  variants: BenchmarkVariantResult[];
  baselineKey: string | null;
}

export const ALL_VARIANTS: VariantSpec[] = [
  { key: 'wasm-fp32', label: 'WASM · FP32', device: 'wasm', dtype: 'fp32' },
  { key: 'wasm-q8', label: 'WASM · INT8', device: 'wasm', dtype: 'q8' },
  { key: 'webgpu-fp16', label: 'WebGPU · FP16', device: 'webgpu', dtype: 'fp16' },
  { key: 'webgpu-q8', label: 'WebGPU · INT8', device: 'webgpu', dtype: 'q8' },
];

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function p95(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * 0.95) - 1);
  return sorted[index];
}

function stats(values: number[]): LatencyStats {
  return {
    median: Math.round(median(values) * 10) / 10,
    p95: Math.round(p95(values) * 10) / 10,
    min: Math.round(Math.min(...values) * 10) / 10,
    max: Math.round(Math.max(...values) * 10) / 10,
  };
}

function scoreQuery(hits: { title: string }[], relevant: string[]): { recall5: number; recall10: number; mrr: number; ndcg10: number } {
  const seen = new Set<string>();
  const ranked: string[] = [];
  for (const hit of hits) {
    if (seen.has(hit.title)) continue;
    seen.add(hit.title);
    ranked.push(hit.title);
    if (ranked.length >= 10) break;
  }
  const rel = new Set(relevant);
  const hit5 = ranked.slice(0, 5).filter((title) => rel.has(title)).length;
  const hit10 = ranked.slice(0, 10).filter((title) => rel.has(title)).length;
  const recall5 = rel.size ? Math.min(1, hit5 / rel.size) : 0;
  const recall10 = rel.size ? Math.min(1, hit10 / rel.size) : 0;
  const firstRank = ranked.findIndex((title) => rel.has(title));
  const mrr = firstRank >= 0 ? 1 / (firstRank + 1) : 0;
  let dcg = 0;
  ranked.forEach((title, index) => {
    if (rel.has(title)) dcg += 1 / Math.log2(index + 2);
  });
  let idcg = 0;
  for (let index = 0; index < Math.min(rel.size, 10); index += 1) idcg += 1 / Math.log2(index + 2);
  const ndcg10 = idcg ? dcg / idcg : 0;
  return { recall5, recall10, mrr, ndcg10 };
}

function averageQuality(rows: ReturnType<typeof scoreQuery>[]): QualityMetrics {
  const n = Math.max(1, rows.length);
  const sum = rows.reduce(
    (acc, row) => ({
      recall5: acc.recall5 + row.recall5,
      recall10: acc.recall10 + row.recall10,
      mrr: acc.mrr + row.mrr,
      ndcg10: acc.ndcg10 + row.ndcg10,
    }),
    { recall5: 0, recall10: 0, mrr: 0, ndcg10: 0 },
  );
  return {
    recall5: Math.round((sum.recall5 / n) * 1000) / 1000,
    recall10: Math.round((sum.recall10 / n) * 1000) / 1000,
    mrr: Math.round((sum.mrr / n) * 1000) / 1000,
    ndcg10: Math.round((sum.ndcg10 / n) * 1000) / 1000,
    evaluatedQueries: rows.length,
    hitQueries: rows.filter((row) => row.recall10 > 0).length,
  };
}

async function loadSample(): Promise<{ docs: SampleDoc[]; queries: SampleQuery[] }> {
  const [docsResponse, queriesResponse] = await Promise.all([
    fetch('/sample-corpus/docs.json'),
    fetch('/sample-corpus/queries.json'),
  ]);
  if (!docsResponse.ok || !queriesResponse.ok) throw new Error('示例语料加载失败');
  return { docs: await docsResponse.json(), queries: await queriesResponse.json() };
}

function modelBytesFor(dtype: string, files: Record<string, number | null>): number | null {
  if (dtype === 'fp32') return files['onnx/model.onnx'] ?? null;
  if (dtype === 'fp16') return files['onnx/model_fp16.onnx'] ?? null;
  return files['onnx/model_quantized.onnx'] ?? null;
}

export async function runBenchmark(
  variantKeys: string[],
  onProgress: (progress: BenchProgress) => void,
): Promise<BenchmarkResult> {
  const startedAt = new Date().toISOString();
  const webgpu = await detectWebGpu();
  const sample = await loadSample();
  const modelStatus = await api.modelStatus();
  const selected = ALL_VARIANTS.filter((variant) => variantKeys.includes(variant.key));
  if (!selected.length) throw new Error('请至少选择一个基准变体');

  const fp32Bytes = modelStatus.files['onnx/model.onnx'] ?? null;
  const variants: BenchmarkVariantResult[] = [];
  const benchTag = Date.now().toString(36).slice(-5);

  for (const variant of selected) {
    onProgress({ variant: variant.label, stage: '模型加载' });
    const result: BenchmarkVariantResult = {
      key: variant.key,
      label: variant.label,
      device: variant.device,
      dtype: variant.dtype,
      status: 'ok',
      modelBytes: modelBytesFor(variant.dtype, modelStatus.files),
      compressionRatio:
        fp32Bytes && modelBytesFor(variant.dtype, modelStatus.files)
          ? Math.round((fp32Bytes / Number(modelBytesFor(variant.dtype, modelStatus.files))) * 100) / 100
          : null,
      loadMs: null,
      warmupMs: null,
      docCount: 0,
      chunkCount: 0,
      embedDocsMs: null,
      embedPerChunkMs: null,
      stageImportMs: null,
      refreshMs: null,
      refreshVerified: null,
      seedMs: null,
      firstQueryE2eMs: null,
      queryEmbedMs: null,
      searchMs: null,
      e2eMs: null,
      quality: null,
    };
    variants.push(result);
    let collectionId: string | null = null;
    let embedder: Embedder | null = null;

    try {
      embedder = await Embedder.create({
        force: { device: variant.device, dtype: variant.dtype },
        warmup: true,
        onLoadProgress: (event) => {
          onProgress({
            variant: variant.label,
            stage: '模型加载',
            detail: event.file ? `${event.file} ${event.progress != null ? `${Math.round(event.progress)}%` : ''}` : undefined,
            progress: event.progress,
          });
        },
      });
      result.loadMs = embedder.status.loadMs != null ? Math.round(embedder.status.loadMs) : null;
      result.warmupMs = embedder.status.warmupMs != null ? Math.round(embedder.status.warmupMs) : null;

      onProgress({ variant: variant.label, stage: '创建临时集合' });
      const created = await api.createCollection(`基准-${variant.key}-${benchTag}`);
      collectionId = created.collection.id;

      const embedStarted = performance.now();
      let stageMs = 0;
      let chunks = 0;
      for (let index = 0; index < sample.docs.length; index += 1) {
        const doc = sample.docs[index];
        onProgress({ variant: variant.label, stage: '文档向量化', detail: `${index + 1}/${sample.docs.length}`, progress: (index / sample.docs.length) * 100 });
        const content = normalizeText(doc.content);
        const pieces = chunkDocument(content, { target: 300, overlap: 60 });
        const inputs = pieces.map((piece) => embedInput(doc.title, piece.text));
        const vectors = await embedder.embed(inputs, { batchSize: 8 });
        const staged = await api.importDocument(collectionId, {
          title: doc.title,
          content,
          chunks: pieces.map((piece, position) => ({ text: piece.text, embedding: vectors[position] })),
          deferRefresh: true,
        });
        chunks += pieces.length;
        stageMs += staged.staged.timings.totalMs;
      }
      result.embedDocsMs = Math.round(performance.now() - embedStarted);
      result.embedPerChunkMs = chunks ? Math.round((result.embedDocsMs / chunks) * 10) / 10 : null;
      result.stageImportMs = Math.round(stageMs);
      result.docCount = sample.docs.length;
      result.chunkCount = chunks;

      onProgress({ variant: variant.label, stage: '刷新索引' });
      const refreshed = await api.refresh(collectionId);
      result.refreshMs = refreshed.refresh.refreshMs;
      result.refreshVerified = refreshed.refresh.verified;

      const detail = await api.getCollection(collectionId);
      if (detail.documents.length !== sample.docs.length) {
        throw new Error(`导入数量不一致：期望 ${sample.docs.length}，实际 ${detail.documents.length}`);
      }

      const runQuery = async (query: string) => {
        const embedStart = performance.now();
        const vector = await embedder!.embedOne(query);
        const embedMs = performance.now() - embedStart;
        const queryStart = performance.now();
        const response = await api.search(collectionId!, { query, embedding: vector, topK: 10 });
        const totalMs = performance.now() - queryStart;
        return { response, embedMs, totalMs };
      };

      onProgress({ variant: variant.label, stage: '预热查询' });
      const seedStart = performance.now();
      await runQuery(sample.queries[0].query);
      await runQuery(sample.queries[1].query);
      result.seedMs = Math.round(performance.now() - seedStart);

      onProgress({ variant: variant.label, stage: '评估检索质量', detail: `0/${sample.queries.length}` });
      const queryEmbedTimes: number[] = [];
      const searchTimes: number[] = [];
      const e2eTimes: number[] = [];
      const qualityRows: ReturnType<typeof scoreQuery>[] = [];
      for (let index = 0; index < sample.queries.length; index += 1) {
        const item = sample.queries[index];
        const { response, embedMs, totalMs } = await runQuery(item.query);
        if (index === 0) result.firstQueryE2eMs = Math.round((embedMs + totalMs) * 10) / 10;
        queryEmbedTimes.push(embedMs);
        searchTimes.push(response.searchMs);
        e2eTimes.push(embedMs + totalMs);
        qualityRows.push(scoreQuery(response.results, item.relevant));
        onProgress({
          variant: variant.label,
          stage: '评估检索质量',
          detail: `${index + 1}/${sample.queries.length}`,
          progress: ((index + 1) / sample.queries.length) * 100,
        });
      }
      result.queryEmbedMs = stats(queryEmbedTimes);
      result.searchMs = stats(searchTimes);
      result.e2eMs = stats(e2eTimes);
      result.quality = averageQuality(qualityRows);
    } catch (error) {
      result.status = 'error';
      result.error = (error as Error).message;
      onProgress({ variant: variant.label, stage: '失败', detail: result.error });
    } finally {
      if (embedder) await embedder.dispose();
      if (collectionId) {
        await api.deleteCollection(collectionId).catch(() => {});
      }
    }
  }

  const baseline =
    variants.find((variant) => variant.status === 'ok' && variant.dtype === 'fp32') ??
    variants.find((variant) => variant.status === 'ok') ??
    null;

  return {
    schemaVersion: 1,
    startedAt,
    finishedAt: new Date().toISOString(),
    userAgent: navigator.userAgent,
    webgpu: { available: webgpu.available, reason: webgpu.reason },
    corpus: { docs: sample.docs.length, queries: sample.queries.length, chunksPerVariant: variants.find((v) => v.status === 'ok')?.chunkCount ?? null },
    modelFiles: modelStatus.files,
    modelBytes: {
      fp32: modelStatus.files['onnx/model.onnx'] ?? 0,
      fp16: modelStatus.files['onnx/model_fp16.onnx'] ?? 0,
      q8: modelStatus.files['onnx/model_quantized.onnx'] ?? 0,
    },
    variants,
    baselineKey: baseline?.key ?? null,
  };
}
