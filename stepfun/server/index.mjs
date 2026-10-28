import fs from 'node:fs/promises';
import path from 'node:path';
import express from 'express';
import { config, ROOT } from './config.mjs';
import {
  closeDb,
  createCollection,
  dbHealth,
  deleteCollection,
  getCollectionMeta,
  getIndexState,
  getSession,
  initDb,
  listCollections,
  listDocuments,
  upsertSession,
} from './db.mjs';
import { deleteDocument, refreshCollection, stageDocument, validatePayload } from './import.mjs';
import { runSearch } from './search.mjs';

const app = express();
app.disable('x-powered-by');
app.use((req, res, next) => {
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  next();
});
app.use(express.json({ limit: '64mb' }));

const asyncRoute = (handler) => (req, res, next) => {
  Promise.resolve(handler(req, res, next)).catch(next);
};

function badRequest(message) {
  const error = new Error(message);
  error.status = 400;
  return error;
}

function notFound(message) {
  const error = new Error(message);
  error.status = 404;
  return error;
}

app.get('/api/health', asyncRoute(async (_req, res) => {
  const db = await dbHealth();
  const { host, port, user, database } = config.seekdb;
  res.json({ ok: true, db, model: config.model, seekdb: { host, port, user, database } });
}));

app.get('/api/model/status', asyncRoute(async (_req, res) => {
  const dir = path.join(ROOT, 'public', 'models', config.model.id);
  const names = [
    'config.json',
    'tokenizer.json',
    'onnx/model.onnx',
    'onnx/model_fp16.onnx',
    'onnx/model_quantized.onnx',
  ];
  const files = {};
  for (const name of names) {
    try {
      const stat = await fs.stat(path.join(dir, name));
      files[name] = stat.size;
    } catch {
      files[name] = null;
    }
  }
  const ready = Boolean(files['tokenizer.json'] && (files['onnx/model.onnx'] || files['onnx/model_quantized.onnx']));
  res.json({ model: config.model, dir: path.relative(ROOT, dir), ready, files });
}));

app.get('/api/collections', asyncRoute(async (_req, res) => {
  res.json({ collections: await listCollections() });
}));

app.post('/api/collections', asyncRoute(async (req, res) => {
  const created = await createCollection(req.body?.name);
  res.status(201).json({ collection: created });
}));

app.delete('/api/collections/:id', asyncRoute(async (req, res) => {
  await deleteCollection(req.params.id);
  res.json({ ok: true });
}));

app.get('/api/collections/:id', asyncRoute(async (req, res) => {
  const meta = await getCollectionMeta(req.params.id);
  if (!meta) throw notFound('集合不存在');
  const [documents, indexState] = await Promise.all([
    listDocuments(meta.id),
    getIndexState(meta.id),
  ]);
  res.json({ collection: meta, documents, indexState });
}));

app.post('/api/collections/:id/import', asyncRoute(async (req, res) => {
  const collectionId = req.params.id;
  const payload = validatePayload(req.body || {});
  if (!(await getCollectionMeta(collectionId))) throw notFound('集合不存在');
  const staged = await stageDocument({ collectionId, ...payload });
  const refresh = req.body?.deferRefresh ? null : await refreshCollection(collectionId);
  res.status(201).json({ staged, refresh });
}));

app.post('/api/collections/:id/refresh', asyncRoute(async (req, res) => {
  if (!(await getCollectionMeta(req.params.id))) throw notFound('集合不存在');
  res.json({ refresh: await refreshCollection(req.params.id) });
}));

app.delete('/api/collections/:id/documents/:docId', asyncRoute(async (req, res) => {
  if (!(await getCollectionMeta(req.params.id))) throw notFound('集合不存在');
  const removed = await deleteDocument(req.params.id, req.params.docId);
  const refresh = await refreshCollection(req.params.id);
  res.json({ removed, refresh });
}));

app.post('/api/collections/:id/search', asyncRoute(async (req, res) => {
  const collectionId = req.params.id;
  if (!(await getCollectionMeta(collectionId))) throw notFound('集合不存在');
  const { query, embedding, topK, sessionId } = req.body || {};
  if (!query) throw badRequest('请输入查询内容');
  if (!Array.isArray(embedding)) throw badRequest('缺少查询向量');
  const result = await runSearch({ collectionId, query, embedding, topK, sessionId });
  res.json(result);
}));

app.get('/api/sessions/:id', asyncRoute(async (req, res) => {
  res.json({ session: await getSession(req.params.id) });
}));

app.patch('/api/sessions/:id', asyncRoute(async (req, res) => {
  const { collectionId, backend, dtype, lastQuery } = req.body || {};
  await upsertSession({ sessionId: req.params.id, collectionId, backend, dtype, lastQuery });
  res.json({ session: await getSession(req.params.id) });
}));

const distDir = config.distDir;
let distReady = false;
try {
  await fs.access(path.join(distDir, 'index.html'));
  distReady = true;
} catch {
  distReady = false;
}

if (distReady) {
  app.use(express.static(distDir, { index: false, maxAge: '1h', setHeaders: (res, filePath) => {
    if (filePath.endsWith('.onnx')) res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
  } }));
  app.get(/^(?!\/api\/).*/, async (req, res, next) => {
    try {
      res.sendFile(path.join(distDir, 'index.html'));
    } catch (error) {
      next(error);
    }
  });
} else {
  app.get('/', (_req, res) => {
    res.status(200).send('前端尚未构建。开发模式请访问 Vite（5173），或运行 npm run build 后重启。');
  });
}

app.use((req, res) => {
  res.status(404).json({ error: 'not found' });
});

app.use((error, _req, res, _next) => {
  const status = error.status || (error.code === 'ERR_INVALID_ARG' ? 400 : 500);
  if (status >= 500) console.error('[api]', error);
  res.status(status).json({ error: error.message || 'internal error' });
});

async function start() {
  await initDb();
  const health = await dbHealth();
  const modelStatus = await fetchModelStatus();
  console.log(`[seekdb] ${health.version} · database=${health.database} · collections=${health.collections}`);
  console.log(`[model] ${config.model.id} · ${modelStatus.ready ? 'files ready' : '模型文件缺失，请先运行 npm run models:fetch'}`);
  if (!distReady) console.log('[web] dist 未构建，仅提供 API（开发时使用 npm run dev）');

  const server = app.listen(config.port, config.host, () => {
    console.log(`[stepfun-kb] http://${config.host}:${config.port}`);
  });

  const shutdown = async (signal) => {
    console.log(`[stepfun-kb] ${signal} received, shutting down`);
    server.close();
    await closeDb();
    process.exit(0);
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

async function fetchModelStatus() {
  try {
    const dir = path.join(ROOT, 'public', 'models', config.model.id);
    await fs.access(path.join(dir, 'tokenizer.json'));
    return { ready: true };
  } catch {
    return { ready: false };
  }
}

start().catch((error) => {
  console.error('[stepfun-kb] 启动失败：', error.message);
  if (/ECONNREFUSED|connect/i.test(error.message)) {
    console.error('请先启动 seekdb：npm run db:start（或检查 SEEKDB_HOST/SEEKDB_PORT）');
  }
  process.exit(1);
});
