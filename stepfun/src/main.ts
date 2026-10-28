import './styles.css';
import { api } from './api';
import { chunkDocument, embedInput, normalizeText } from './chunker';
import { Embedder } from './embedding/embedder';
import { detectWebGpu } from './embedding/backend';
import { runBenchmark, type BenchmarkResult, type BenchProgress } from './bench/run';
import type {
  BackendStatus,
  CollectionDetail,
  CollectionInfo,
  ModelStatus,
  SampleDoc,
  SampleQuery,
  SearchResponse,
  SessionInfo,
} from './types';

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char] as string);
}

function formatMs(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`;
}

function formatTime(timestamp: number | null | undefined): string {
  if (!timestamp) return '—';
  return new Date(timestamp).toLocaleString('zh-CN', { hour12: false });
}

function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '—';
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
}

function ensureSessionId(): string {
  const key = 'stepfun.sessionId';
  let value = localStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID ? crypto.randomUUID() : `s_${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(key, value);
  }
  return value;
}

async function sha256Hex(text: string): Promise<string | undefined> {
  if (!crypto.subtle) return undefined;
  try {
    const data = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
  } catch {
    return undefined;
  }
}

type EmbedderState = 'idle' | 'loading' | 'ready' | 'error';

const state = {
  sessionId: ensureSessionId(),
  collections: [] as CollectionInfo[],
  collectionId: null as string | null,
  detail: null as CollectionDetail | null,
  embedder: null as Embedder | null,
  embedderState: 'idle' as EmbedderState,
  embedderError: '',
  modelStatus: null as ModelStatus | null,
  health: null as any,
  session: null as SessionInfo | null,
  benchmark: null as BenchmarkResult | null,
  benchRunning: false,
  importing: false,
};

let bootPromise: Promise<void> = Promise.resolve();

function toast(message: string, kind: 'ok' | 'error' | 'info' = 'info', timeout = 4200): void {
  const node = $('toast');
  node.textContent = message;
  node.className = `toast ${kind === 'info' ? '' : kind}`.trim();
  node.hidden = false;
  window.clearTimeout((toast as any).timer);
  (toast as any).timer = window.setTimeout(() => { node.hidden = true; }, timeout);
}

function showNotice(message: string, kind: 'info' | 'error' | 'ok' = 'info'): void {
  const node = $('notice');
  node.textContent = message;
  node.className = `notice ${kind === 'info' ? '' : kind}`.trim();
  node.hidden = !message;
}

function setBackendBadge(status: BackendStatus | null, loading = false): void {
  const badge = $('backend-badge');
  if (loading) {
    badge.className = 'badge loading';
    badge.textContent = '加载本地模型…';
    badge.title = '';
    return;
  }
  if (!status) {
    badge.className = 'badge';
    badge.textContent = '后端未就绪';
    return;
  }
  const ok = status.backend === 'webgpu';
  badge.className = `badge ${ok ? 'ok' : 'warn'}`;
  badge.textContent = status.label;
  badge.title = `${status.reason}${status.attempts?.length ? `；尝试：${status.attempts.map((a) => `${a.candidate}${a.ok ? '✓' : '✗'}`).join('，')}` : ''}`;
}

function updateButtons(): void {
  const ready = state.embedderState === 'ready';
  const hasCollection = Boolean(state.collectionId);
  const hasDocs = Boolean(state.detail?.documents?.length);
  $<HTMLButtonElement>('import-button').disabled = !ready || !hasCollection || state.importing;
  $<HTMLButtonElement>('sample-button').disabled = !ready || !hasCollection || state.importing;
  $<HTMLButtonElement>('refresh-index').disabled = !hasCollection || state.importing || state.benchRunning;
  $<HTMLButtonElement>('search-button').disabled = !ready || !hasCollection || !hasDocs || state.importing;
  $('import-hint').textContent = !ready
    ? state.embedderState === 'error' ? '模型加载失败' : '模型加载完成后可导入'
    : !hasCollection ? '请先创建或选择集合' : '浏览器内切块 + 向量化';
}

function renderCollections(): void {
  const list = $('collections');
  list.innerHTML = '';
  $('collection-count').textContent = String(state.collections.length);
  if (!state.collections.length) {
    list.innerHTML = '<li class="empty">还没有集合</li>';
    return;
  }
  for (const collection of state.collections) {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.className = `collection-item${collection.id === state.collectionId ? ' active' : ''}`;
    button.innerHTML = `<strong>${escapeHtml(collection.name)}</strong><span>${collection.docCount} 篇 · ${collection.chunkCount} 块 ${collection.verified ? '· 已验证' : ''}</span>`;
    button.addEventListener('click', () => { void selectCollection(collection.id); });
    const remove = document.createElement('button');
    remove.className = 'icon-button';
    remove.title = '删除集合';
    remove.textContent = '×';
    remove.addEventListener('click', async (event) => {
      event.stopPropagation();
      if (!confirm(`删除集合「${collection.name}」及其全部文档？`)) return;
      try {
        await api.deleteCollection(collection.id);
        if (state.collectionId === collection.id) {
          state.collectionId = null;
          state.detail = null;
          localStorage.removeItem('stepfun.collectionId');
          $('results').innerHTML = '';
          $('search-meta').textContent = '等待选择集合';
        }
        await reloadCollections();
        if (!state.collectionId && state.collections.length) await selectCollection(state.collections[0].id);
        renderAll();
        toast('集合已删除', 'ok');
      } catch (error) {
        toast((error as Error).message, 'error');
      }
    });
    li.append(button, remove);
    list.append(li);
  }
}

function renderDocuments(): void {
  const list = $('documents');
  const documents = state.detail?.documents ?? [];
  $('doc-count').textContent = String(documents.length);
  list.innerHTML = '';
  if (!documents.length) {
    list.innerHTML = '<li class="empty">当前集合还没有文档</li>';
  } else {
    for (const doc of documents) {
      const li = document.createElement('li');
      const box = document.createElement('div');
      box.className = 'doc-item';
      box.innerHTML = `<strong title="${escapeHtml(doc.title)}">${escapeHtml(doc.title)}</strong><span>${doc.charCount} 字 · ${doc.chunkCount} 块 · ${formatTime(doc.importedAt)}</span>`;
      const remove = document.createElement('button');
      remove.className = 'icon-button';
      remove.title = '删除文档';
      remove.textContent = '×';
      remove.addEventListener('click', async () => {
        if (!confirm(`删除文档「${doc.title}」？`)) return;
        try {
          const response = await api.deleteDocument(state.collectionId!, doc.docId);
          await reloadCollections();
          await reloadDetail();
          renderAll();
          toast(`已删除 ${response.removed.deletedChunks} 个块，刷新 ${response.refresh.refreshMs} ms`, 'ok');
        } catch (error) {
          toast((error as Error).message, 'error');
        }
      });
      li.append(box, remove);
      list.append(li);
    }
  }

  const indexState = state.detail?.indexState;
  const node = $('index-state');
  if (!state.collectionId) {
    node.textContent = '尚未选择集合';
  } else if (!documents.length) {
    node.innerHTML = '<span class="muted">暂无索引数据</span>';
  } else {
    const verified = Boolean(indexState?.verified);
    node.innerHTML = [
      `<span>${documents.length} 篇文档 · ${indexState?.chunkCount ?? 0} 个块</span>`,
      `<span>最近刷新：${formatTime(indexState?.lastRefreshAt)}（${formatMs(indexState?.refreshMs)}）</span>`,
      `<span class="${verified ? 'ok' : 'pending'}">${verified ? '✓ 刷新后已验证新增内容可检索' : '⚠ 尚未验证刷新结果'}</span>`,
    ].join('');
  }
  $('session-info').innerHTML = [
    `<div>会话 <code>${escapeHtml(state.sessionId.slice(0, 8))}…</code></div>`,
    `<div>集合：${escapeHtml(state.detail?.collection?.name ?? '未选择')}</div>`,
    `<div>后端：${escapeHtml(state.embedder?.status.label ?? '加载中')}</div>`,
    `<div>最近查询：${escapeHtml(state.session?.lastQuery ?? '—')}</div>`,
  ].join('');
}

function renderAll(): void {
  renderCollections();
  renderDocuments();
  updateButtons();
}

async function reloadCollections(): Promise<void> {
  const response = await api.listCollections();
  state.collections = response.collections;
}

async function reloadDetail(): Promise<void> {
  if (!state.collectionId) {
    state.detail = null;
    return;
  }
  try {
    state.detail = await api.getCollection(state.collectionId);
  } catch {
    state.detail = null;
    state.collectionId = null;
  }
}

async function selectCollection(id: string): Promise<void> {
  state.collectionId = id;
  localStorage.setItem('stepfun.collectionId', id);
  await reloadDetail();
  renderAll();
  $('results').innerHTML = '';
  $('search-meta').textContent = state.detail?.documents.length ? '输入问题开始检索' : '当前集合没有文档，先导入或导入示例语料';
  await api.patchSession(state.sessionId, {
    collectionId: id,
    ...(state.embedder ? { backend: state.embedder.status.backend, dtype: state.embedder.status.dtype } : {}),
  }).catch(() => {});
  state.session = (await api.getSession(state.sessionId).catch(() => ({ session: null }))).session;
  renderDocuments();
}

async function createCollection(name?: string): Promise<CollectionInfo> {
  const input = $<HTMLInputElement>('collection-name');
  const finalName = (name ?? input.value).trim() || `知识库 ${state.collections.length + 1}`;
  const response = await api.createCollection(finalName);
  input.value = '';
  await reloadCollections();
  await selectCollection(response.collection.id);
  toast(`已创建集合「${response.collection.name}」`, 'ok');
  return response.collection;
}

interface ProgressLine {
  update: (stage: string, detail?: string) => void;
  done: (detail?: string) => void;
  fail: (message: string) => void;
}

function createProgressLine(title: string): ProgressLine {
  const container = $('import-progress');
  const node = document.createElement('div');
  node.className = 'progress-item';
  node.innerHTML = `<span class="dot"></span><div class="body"><div class="line"><span class="title">${escapeHtml(title)}</span><span class="detail">准备中…</span></div></div>`;
  container.append(node);
  container.scrollTop = container.scrollHeight;
  const detailNode = node.querySelector('.detail') as HTMLElement;
  return {
    update(stage, detail) {
      detailNode.textContent = detail ? `${stage} · ${detail}` : stage;
    },
    done(detail) {
      node.classList.add('ok');
      detailNode.textContent = detail ?? '完成';
    },
    fail(message) {
      node.classList.add('error');
      detailNode.textContent = message;
    },
  };
}

async function importOne(
  title: string,
  content: string,
  options: { refresh?: boolean; lineTitle?: string } = {},
): Promise<{ chunks: number; refreshMs: number | null; verified: boolean | null }> {
  if (!state.embedder) throw new Error('模型尚未就绪');
  if (!state.collectionId) throw new Error('请先选择集合');
  const normalizedTitle = title.trim();
  const normalizedContent = normalizeText(content);
  if (!normalizedTitle) throw new Error('请填写标题');
  if (normalizedContent.length < 20) throw new Error('正文至少需要 20 个字符');

  const line = createProgressLine(options.lineTitle ?? normalizedTitle);
  try {
    const chunks = chunkDocument(normalizedContent, { target: 300, overlap: 60 });
    if (!chunks.length) throw new Error('切块结果为空');
    line.update('切块完成', `${chunks.length} 个分块，${normalizedContent.length} 字`);

    const inputs = chunks.map((chunk) => embedInput(normalizedTitle, chunk.text));
    const started = performance.now();
    const vectors = await state.embedder.embed(inputs, {
      batchSize: 8,
      onProgress: (done, total) => line.update('浏览器向量化', `${done}/${total} 个分块`),
    });
    const embedMs = performance.now() - started;
    line.update('写入 seekdb', `${chunks.length} 个向量（${formatMs(embedMs)}）`);

    const contentHash = await sha256Hex(normalizedContent);
    const response = await api.importDocument(state.collectionId, {
      title: normalizedTitle,
      content: normalizedContent,
      ...(contentHash ? { contentHash } : {}),
      chunks: chunks.map((chunk, index) => ({ text: chunk.text, embedding: vectors[index] })),
      deferRefresh: true,
    });

    let refreshMs: number | null = null;
    let verified: boolean | null = null;
    if (options.refresh !== false) {
      line.update('刷新索引');
      const refreshed = await api.refresh(state.collectionId);
      refreshMs = refreshed.refresh.refreshMs;
      verified = refreshed.refresh.verified;
      line.done(
        `完成 · ${chunks.length} 块 · 向量化 ${formatMs(embedMs)} · 写入 ${formatMs(response.staged.timings.addMs)} · 刷新 ${formatMs(refreshMs)}${verified ? ' · 已验证可检索' : ' · 未通过检索验证'}`,
      );
    } else {
      line.done(`已写入 ${chunks.length} 块 · 等待批量刷新`);
    }

    await reloadCollections();
    await reloadDetail();
    renderAll();
    return { chunks: chunks.length, refreshMs, verified };
  } catch (error) {
    line.fail((error as Error).message);
    throw error;
  }
}

async function importCurrent(): Promise<void> {
  const title = $<HTMLInputElement>('doc-title').value;
  const content = $<HTMLTextAreaElement>('doc-content').value;
  if (!title.trim() || !content.trim()) {
    toast('请填写标题与正文', 'error');
    return;
  }
  state.importing = true;
  updateButtons();
  try {
    const result = await importOne(title, content, { refresh: true });
    $<HTMLInputElement>('doc-title').value = '';
    $<HTMLTextAreaElement>('doc-content').value = '';
    toast(`导入完成：${result.chunks} 个分块，刷新 ${formatMs(result.refreshMs)}${result.verified ? '，已验证可检索' : ''}`, result.verified ? 'ok' : 'info');
  } catch (error) {
    toast((error as Error).message, 'error');
  } finally {
    state.importing = false;
    updateButtons();
  }
}

async function importSample(): Promise<void> {
  if (!state.collectionId || !state.embedder) return;
  state.importing = true;
  updateButtons();
  $('import-progress').innerHTML = '';
  try {
    const [docsResponse, queriesResponse] = await Promise.all([
      fetch('/sample-corpus/docs.json'),
      fetch('/sample-corpus/queries.json'),
    ]);
    if (!docsResponse.ok) throw new Error('示例语料读取失败');
    const docs = (await docsResponse.json()) as SampleDoc[];
    const queries = (await queriesResponse.json()) as SampleQuery[];
    void queries;
    const existing = new Set((state.detail?.documents ?? []).map((doc) => doc.title));
    const pending = docs.filter((doc) => !existing.has(doc.title));
    if (!pending.length) {
      toast('示例语料已全部导入', 'info');
      return;
    }
    let failures = 0;
    for (const doc of pending) {
      try {
        await importOne(doc.title, doc.content, { refresh: false });
      } catch {
        failures += 1;
      }
    }
    const line = createProgressLine('批量刷新索引');
    line.update('刷新索引', `${pending.length - failures} 篇新文档`);
    const refreshed = await api.refresh(state.collectionId);
    line.done(`刷新 ${formatMs(refreshed.refresh.refreshMs)} · ${refreshed.refresh.verified ? '已验证新增内容可检索' : '验证未通过'} · ${refreshed.refresh.storedChunks} 块入库`);
    await reloadCollections();
    await reloadDetail();
    renderAll();
    if (failures) toast(`示例语料导入完成，${failures} 篇失败`, 'error');
    else toast(`已导入 ${pending.length} 篇示例文档，刷新 ${formatMs(refreshed.refresh.refreshMs)}`, 'ok');
    if (state.detail?.documents.length) {
      const probe = await performSearch('混合检索如何在数据库内部完成');
      if (!probe.results.length) toast('刷新后检索未返回结果，请检查索引状态', 'error');
    }
  } catch (error) {
    toast((error as Error).message, 'error');
  } finally {
    state.importing = false;
    updateButtons();
  }
}

function highlight(text: string, terms: string[]): string {
  const escaped = escapeHtml(text);
  const unique = [...new Set(terms.filter((term) => term.length >= 2))].slice(0, 8);
  if (!unique.length) return escaped;
  const pattern = new RegExp(unique.map((term) => escapeHtml(term).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'gi');
  return escaped.replace(pattern, (match) => `<mark>${match}</mark>`);
}

function renderSearch(response: SearchResponse, embedMs: number, totalMs: number, query: string): void {
  const list = $('results');
  list.innerHTML = '';
  const terms = response.sanitizedQuery.split(' ').filter(Boolean);
  if (!response.results.length) {
    list.innerHTML = '<li class="empty">没有命中结果。尝试换一个关键词，或确认索引已刷新。</li>';
  } else {
    response.results.forEach((hit, index) => {
      const li = document.createElement('li');
      li.className = 'result-item';
      li.innerHTML = `
        <h4><span class="rank">#${index + 1}</span>${highlight(hit.title, terms)}<span class="chunk-tag">块 ${hit.chunkIndex + 1}</span></h4>
        <p>${highlight(hit.text, terms)}</p>
        <div class="result-sub"><span>doc ${escapeHtml(hit.docId.slice(0, 12))}…</span><span>distance ${hit.distance == null ? '—' : hit.distance.toFixed(4)}</span></div>`;
      list.append(li);
    });
  }
  $('search-meta').innerHTML = [
    `查询 <strong>${escapeHtml(query)}</strong> · 向量化 <strong>${formatMs(embedMs)}</strong> · seekdb RRF <strong>${formatMs(response.searchMs)}</strong> · 端到端 ${formatMs(totalMs)}`,
    `<span class="muted">候选 ${response.candidateK} · 清洗后 query “${escapeHtml(response.sanitizedQuery)}” · ${response.engine}/${response.fusion}</span>`,
  ].join('<br/>');
}

async function performSearch(query: string): Promise<SearchResponse> {
  if (!state.embedder) throw new Error('模型尚未就绪');
  if (!state.collectionId) throw new Error('请先选择集合');
  const text = query.trim();
  if (!text) throw new Error('请输入查询内容');
  const embedStarted = performance.now();
  const vector = await state.embedder.embedOne(text);
  const embedMs = performance.now() - embedStarted;
  const started = performance.now();
  const topK = Number($<HTMLSelectElement>('topk').value) || 8;
  const response = await api.search(state.collectionId, {
    query: text,
    embedding: vector,
    topK,
    sessionId: state.sessionId,
  });
  const totalMs = performance.now() - started + embedMs;
  renderSearch(response, embedMs, totalMs, text);
  state.session = (await api.getSession(state.sessionId).catch(() => ({ session: null }))).session;
  renderDocuments();
  return response;
}

async function refreshIndex(): Promise<void> {
  if (!state.collectionId) return;
  try {
    const response = await api.refresh(state.collectionId);
    await reloadCollections();
    await reloadDetail();
    renderAll();
    toast(`刷新完成 ${formatMs(response.refresh.refreshMs)}${response.refresh.verified ? '，验证通过' : '，验证未通过'}`, response.refresh.verified ? 'ok' : 'error');
  } catch (error) {
    toast((error as Error).message, 'error');
  }
}

function renderAbout(): void {
  const model = state.modelStatus;
  const files = model?.files ?? {};
  const fp32 = files['onnx/model.onnx'] ?? null;
  const fp16 = files['onnx/model_fp16.onnx'] ?? null;
  const q8 = files['onnx/model_quantized.onnx'] ?? null;
  const rows = [
    ['模型', model?.model.upstream ?? 'BAAI/bge-small-zh-v1.5'],
    ['ONNX 仓库 / revision', model ? `${model.model.onnxRepo} @ ${model.model.revision.slice(0, 8)}` : '—'],
    ['向量维度 / 池化', `${model?.model.dimension ?? 512} 维 / CLS + L2 normalize`],
    ['FP32 文件', `${formatBytes(fp32)}（基线）`],
    ['FP16 文件', `${formatBytes(fp16)}${fp32 && fp16 ? ` · 压缩比 ${(fp32 / fp16).toFixed(2)}×` : ''}`],
    ['INT8 文件（动态量化）', `${formatBytes(q8)}${fp32 && q8 ? ` · 压缩比 ${(fp32 / q8).toFixed(2)}×` : ''}`],
    ['当前实际后端', state.embedder?.status.label ?? (state.embedderState === 'loading' ? '加载中…' : '未就绪')],
  ];
  $('about-model').innerHTML = rows
    .map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(String(value))}</td></tr>`)
    .join('');
  if (state.health) {
    $('about-health').textContent = `seekdb ${state.health.db.version} · 数据库 ${state.health.db.database} · ${state.health.db.metadataTables} 张元数据表 · ${state.health.db.collections} 个集合`;
  }
}

function renderBenchCapabilities(): void {
  const node = $('bench-capabilities');
  const gpu = state.embedder?.status;
  const status = gpu
    ? `${gpu.label}（${gpu.reason}）`
    : state.embedderState === 'loading' ? '检测中…' : '未就绪';
  node.innerHTML = [
    `<span class="chip">当前后端：${escapeHtml(status)}</span>`,
    `<span class="chip">模型：bge-small-zh-v1.5 · 512 维</span>`,
    `<span class="chip">评估集：24 篇文档 / 22 条查询</span>`,
  ].join('');
  const webgpu = state.embedder?.status.webgpuDetected ?? false;
  const fp16Box = document.querySelector<HTMLInputElement>('input[data-variant="webgpu-fp16"]');
  const q8Box = document.querySelector<HTMLInputElement>('input[data-variant="webgpu-q8"]');
  if (fp16Box) fp16Box.disabled = !webgpu;
  if (q8Box) q8Box.disabled = !webgpu;
}

function qualityCell(value: number | undefined, baseline: number | undefined): string {
  if (value == null) return '—';
  let text = value.toFixed(3);
  if (baseline != null && baseline !== value) {
    const delta = value - baseline;
    text += ` (${delta >= 0 ? '+' : ''}${delta.toFixed(3)})`;
  }
  return `<span class="${value >= 0.7 ? 'quality-good' : value >= 0.4 ? '' : 'quality-warn'}">${text}</span>`;
}

function renderBenchmark(result: BenchmarkResult): void {
  const baseline = result.variants.find((variant) => variant.key === result.baselineKey);
  const node = $('bench-results');
  const rows = result.variants.map((variant) => {
    if (variant.status === 'error') {
      return `<tr><td>${escapeHtml(variant.label)}</td><td colspan="12" class="quality-warn">失败：${escapeHtml(variant.error ?? '未知错误')}</td></tr>`;
    }
    const q = variant.quality;
    return `<tr>
      <td><strong>${escapeHtml(variant.label)}</strong></td>
      <td class="num">${formatBytes(variant.modelBytes)}</td>
      <td class="num">${variant.compressionRatio ? `${variant.compressionRatio.toFixed(2)}×` : '—'}</td>
      <td class="num">${qualityCell(q?.recall5, baseline?.quality?.recall5)}</td>
      <td class="num">${qualityCell(q?.recall10, baseline?.quality?.recall10)}</td>
      <td class="num">${qualityCell(q?.ndcg10, baseline?.quality?.ndcg10)}</td>
      <td class="num">${formatMs(variant.loadMs)}</td>
      <td class="num">${formatMs(variant.embedDocsMs)}</td>
      <td class="num">${formatMs(variant.refreshMs)}</td>
      <td class="num">${variant.queryEmbedMs ? `${formatMs(variant.queryEmbedMs.median)} / ${formatMs(variant.queryEmbedMs.p95)}` : '—'}</td>
      <td class="num">${variant.searchMs ? `${formatMs(variant.searchMs.median)} / ${formatMs(variant.searchMs.p95)}` : '—'}</td>
      <td class="num">${variant.e2eMs ? `${formatMs(variant.e2eMs.median)} / ${formatMs(variant.e2eMs.p95)}` : '—'}</td>
      <td class="num">${formatMs(variant.seedMs)}</td>
    </tr>`;
  });
  node.innerHTML = `
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr>
          <th>变体</th><th>模型体积</th><th>压缩比</th><th>Recall@5</th><th>Recall@10</th><th>nDCG@10</th>
          <th>加载</th><th>文档向量化</th><th>刷新</th><th>查询向量化 P50/P95</th><th>seekdb 检索 P50/P95</th><th>端到端 P50/P95</th><th>预热</th>
        </tr></thead>
        <tbody>${rows.join('')}</tbody>
      </table>
    </div>
    <p class="hint">质量指标为文档级（按标题去重，取前 10 篇），基线为 ${escapeHtml(baseline?.label ?? '首个成功变体')}；括号内为相对基线的差值。延迟统计基于 22 条查询，预热不计入。</p>`;
  $<HTMLButtonElement>('bench-download').disabled = false;
}

async function runBench(keysArg?: string[]): Promise<BenchmarkResult | null> {
  if (state.benchRunning) return state.benchmark;
  const selected = keysArg?.length
    ? keysArg
    : [...document.querySelectorAll<HTMLInputElement>('input[data-variant]:checked')].map((input) => input.dataset.variant as string);
  if (!selected.length) {
    toast('请至少选择一个基准变体', 'error');
    return null;
  }
  state.benchRunning = true;
  $<HTMLButtonElement>('bench-run').disabled = true;
  $<HTMLButtonElement>('bench-download').disabled = true;
  $('bench-results').innerHTML = '';
  $('bench-progress').innerHTML = '';
  const progressMap = new Map<string, ProgressLine>();
  const onProgress = (event: BenchProgress) => {
    let line = progressMap.get(event.variant);
    if (!line) {
      line = createProgressLine(event.variant);
      progressMap.set(event.variant, line);
    }
    const detail = [event.detail, event.progress != null && event.progress > 0 && event.progress < 100 ? `${Math.round(event.progress)}%` : undefined].filter(Boolean).join(' · ');
    line.update(event.stage, detail || undefined);
    if (event.stage === '失败') line.fail(event.detail ?? '失败');
  };
  try {
    const result = await runBenchmark(selected, onProgress);
    state.benchmark = result;
    for (const variant of result.variants) {
      const line = progressMap.get(variant.label);
      if (!line) continue;
      if (variant.status === 'ok') {
        line.done(`完成 · Recall@10 ${variant.quality?.recall10.toFixed(3) ?? '—'} · 端到端 P50 ${formatMs(variant.e2eMs?.median)}`);
      }
    }
    renderBenchmark(result);
    toast('基准测试完成', 'ok');
    return result;
  } catch (error) {
    toast((error as Error).message, 'error');
    return null;
  } finally {
    state.benchRunning = false;
    $<HTMLButtonElement>('bench-run').disabled = false;
    updateButtons();
  }
}

function downloadBenchmark(): void {
  if (!state.benchmark) return;
  const blob = new Blob([JSON.stringify(state.benchmark, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `stepfun-benchmark-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function bindTabs(): void {
  document.querySelectorAll<HTMLButtonElement>('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((node) => node.classList.toggle('active', node === tab));
      const target = tab.dataset.tab;
      for (const panel of document.querySelectorAll<HTMLElement>('.tab-panel')) {
        panel.hidden = panel.id !== `tab-${target}`;
        panel.classList.toggle('active', panel.id === `tab-${target}`);
      }
      if (target === 'bench') renderBenchCapabilities();
      if (target === 'about') renderAbout();
    });
  });
}

function bindEvents(): void {
  bindTabs();
  $('create-collection').addEventListener('click', async () => {
    try { await createCollection(); } catch (error) { toast((error as Error).message, 'error'); }
  });
  $('collection-name').addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') return;
    try { await createCollection(); } catch (error) { toast((error as Error).message, 'error'); }
  });
  $('doc-file').addEventListener('change', async (event) => {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const text = await file.text();
    $<HTMLTextAreaElement>('doc-content').value = text;
    if (!$<HTMLInputElement>('doc-title').value) {
      $<HTMLInputElement>('doc-title').value = file.name.replace(/\.(txt|md|markdown)$/i, '');
    }
  });
  $('import-button').addEventListener('click', () => { void importCurrent(); });
  $('sample-button').addEventListener('click', () => { void importSample(); });
  $('refresh-index').addEventListener('click', () => { void refreshIndex(); });
  $('search-button').addEventListener('click', async () => {
    try { await performSearch($<HTMLInputElement>('query-input').value); } catch (error) { toast((error as Error).message, 'error'); }
  });
  $('query-input').addEventListener('keydown', async (event) => {
    if (event.key !== 'Enter') return;
    try { await performSearch($<HTMLInputElement>('query-input').value); } catch (error) { toast((error as Error).message, 'error'); }
  });
  $('bench-run').addEventListener('click', () => { void runBench(); });
  $('bench-download').addEventListener('click', downloadBenchmark);
  $('wasm-toggle').addEventListener('click', (event) => {
    event.preventDefault();
    const url = new URL(window.location.href);
    if (url.searchParams.get('backend') === 'wasm') url.searchParams.delete('backend');
    else url.searchParams.set('backend', 'wasm');
    window.location.href = url.toString();
  });
}

async function loadEmbedder(): Promise<void> {
  state.embedderState = 'loading';
  setBackendBadge(null, true);
  updateButtons();
  renderBenchCapabilities();
  const webgpu = await detectWebGpu();
  try {
    const embedder = await Embedder.create({
      onLoadProgress: (event) => {
        if (event.progress != null && event.file) {
          $('backend-badge').textContent = `加载模型 ${Math.round(event.progress)}%`;
        }
      },
      onAttempt: (candidate, ok, error) => {
        if (!ok) console.warn(`[embedder] ${candidate.device}/${candidate.dtype} 失败：${error}`);
      },
    });
    state.embedder = embedder;
    state.embedderState = 'ready';
    state.embedderError = '';
    setBackendBadge(embedder.status);
    if (webgpu.available && embedder.status.backend === 'wasm') {
      showNotice(`WebGPU 不可用，已自动降级到 ${embedder.status.label}。原因：${embedder.status.reason}`, 'info');
    } else if (webgpu.forced) {
      showNotice('已通过 URL 参数强制使用 WASM 后端。', 'info');
    } else {
      showNotice('');
    }
    await api.patchSession(state.sessionId, {
      collectionId: state.collectionId ?? undefined,
      backend: embedder.status.backend,
      dtype: embedder.status.dtype,
    }).catch(() => {});
    state.session = (await api.getSession(state.sessionId).catch(() => ({ session: null }))).session;
    renderDocuments();
    renderAbout();
    renderBenchCapabilities();
    toast(`推理后端就绪：${embedder.status.label}`, 'ok');
  } catch (error) {
    state.embedderState = 'error';
    state.embedderError = (error as Error).message;
    setBackendBadge(null);
    $('backend-badge').className = 'badge error';
    $('backend-badge').textContent = '模型加载失败';
    showNotice(`本地模型加载失败：${state.embedderError}`, 'error');
    toast('本地模型加载失败，请检查模型与 ORT 资源', 'error');
  } finally {
    updateButtons();
    renderAbout();
  }
}

async function boot(): Promise<void> {
  bindEvents();
  $<HTMLButtonElement>('sample-button').disabled = true;
  try {
    state.health = await api.health();
    $('footer-status').textContent = `seekdb ${state.health.db.version} · 本地推理`;
  } catch (error) {
    showNotice('无法连接本地 API。请先启动 seekdb 与后端：npm run db:start && npm start', 'error');
    throw error;
  }

  const [modelStatus, collectionsResponse, sessionResponse] = await Promise.all([
    api.modelStatus(),
    api.listCollections(),
    api.getSession(state.sessionId),
  ]);
  state.modelStatus = modelStatus;
  state.collections = collectionsResponse.collections;
  state.session = sessionResponse.session;
  $('model-badge').textContent = `${modelStatus.model.id} · ${modelStatus.model.dimension}d`;
  if (!modelStatus.ready) {
    showNotice('模型文件缺失：运行 npm run models:fetch，然后刷新页面。', 'error');
  }
  renderAbout();

  let desired = sessionResponse.session?.collectionId ?? localStorage.getItem('stepfun.collectionId');
  if (!state.collections.length) {
    const created = await createCollection('我的知识库').catch(() => null);
    desired = created?.id ?? null;
  }
  if (!desired || !state.collections.some((collection) => collection.id === desired)) {
    desired = state.collections[0]?.id ?? null;
  }
  if (desired) await selectCollection(desired);
  renderAll();

  const embedderTask = loadEmbedder();
  window.__stepfun = {
    ready: Promise.all([embedderTask]).then(() => undefined),
    state: () => ({
      sessionId: state.sessionId,
      collectionId: state.collectionId,
      embedderState: state.embedderState,
      embedder: state.embedder?.status ?? null,
      collections: state.collections,
      detail: state.detail,
      session: state.session,
      benchmark: state.benchmark,
    }),
    importText: (title: string, content: string) => importOne(title, content, { refresh: true }),
    search: (query: string) => performSearch(query),
    createCollection: (name: string) => createCollection(name),
    selectCollection: (id: string) => selectCollection(id),
    refresh: () => refreshIndex(),
    benchmark: (keys: string[]) => runBench(keys),
    runBenchSelected: () => runBench(),
    getBenchmark: () => state.benchmark,
    modelStatus: () => state.modelStatus,
  };
  await embedderTask;
}

declare global {
  interface Window {
    __stepfun?: {
      ready: Promise<void>;
      state: () => any;
      importText: (title: string, content: string) => Promise<{ chunks: number; refreshMs: number | null; verified: boolean | null }>;
      search: (query: string) => Promise<SearchResponse>;
      createCollection: (name: string) => Promise<CollectionInfo>;
      selectCollection: (id: string) => Promise<void>;
      refresh: () => Promise<void>;
      benchmark: (keys: string[]) => Promise<BenchmarkResult | null>;
      runBenchSelected: () => Promise<BenchmarkResult | null>;
      getBenchmark: () => BenchmarkResult | null;
      modelStatus: () => ModelStatus | null;
    };
  }
}

bootPromise = boot().catch((error) => {
  console.error(error);
  showNotice(`初始化失败：${(error as Error).message}`, 'error');
});

void bootPromise;
