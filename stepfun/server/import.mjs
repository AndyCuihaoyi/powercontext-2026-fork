import crypto from 'node:crypto';
import { config } from './config.mjs';
import {
  getCollectionMeta,
  getDocument,
  getLatestDocument,
  getPool,
  getSeekdbCollection,
  markImport,
  upsertDocument,
  deleteDocumentRow,
  refreshIndexState,
} from './db.mjs';
import { probeSnippet, sanitizeQuery } from './text.mjs';

const ADD_BATCH = 32;
const ID_BATCH = 256;
const MAX_CHUNKS = 1200;

function toIdList(count, prefix) {
  return Array.from({ length: count }, (_, index) => `${prefix}__${index}`);
}

function batches(items, size) {
  const out = [];
  for (let index = 0; index < items.length; index += size) {
    out.push(items.slice(index, index + size));
  }
  return out;
}

function validateEmbedding(vector, index) {
  if (!Array.isArray(vector) || vector.length !== config.model.dimension) {
    throw new Error(`第 ${index + 1} 个分块向量维度必须为 ${config.model.dimension}`);
  }
  let norm = 0;
  for (const value of vector) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      throw new Error(`第 ${index + 1} 个分块向量包含非法数值`);
    }
    norm += value * value;
  }
  norm = Math.sqrt(norm);
  if (norm < 0.5 || norm > 1.5) {
    throw new Error(`第 ${index + 1} 个分块向量未归一化（L2 范数 ${norm.toFixed(3)}）`);
  }
}

export function validatePayload(payload) {
  const title = String(payload?.title ?? '').trim();
  const content = String(payload?.content ?? '').replace(/\r\n/g, '\n').trim();
  const chunks = payload?.chunks;

  if (title.length < 1 || title.length > 120) throw new Error('标题需为 1–120 个字符');
  if (content.length < 20) throw new Error('正文至少需要 20 个字符');
  if (content.length > 200_000) throw new Error('单个文档正文不能超过 200000 个字符');
  if (!Array.isArray(chunks) || chunks.length < 1) throw new Error('至少需要一个分块');
  if (chunks.length > MAX_CHUNKS) throw new Error(`单个文档分块不能超过 ${MAX_CHUNKS} 个`);

  const contentHash = crypto.createHash('sha256').update(content, 'utf8').digest('hex');
  if (payload?.contentHash && payload.contentHash !== contentHash) {
    throw new Error('正文哈希不一致：客户端与服务端内容不同步');
  }

  const normalized = chunks.map((chunk, index) => {
    const text = String(chunk?.text ?? '');
    if (text.length < 1 || text.length > 1000) {
      throw new Error(`第 ${index + 1} 个分块长度非法`);
    }
    if (!content.includes(text)) {
      throw new Error(`第 ${index + 1} 个分块与正文不一致`);
    }
    validateEmbedding(chunk?.embedding, index);
    return { text, embedding: chunk.embedding };
  });

  return { title, content, contentHash, chunks: normalized };
}

async function idsForDoc(collection, docId) {
  const ids = [];
  const pageSize = 1000;
  for (let offset = 0; offset < 10_000; offset += pageSize) {
    const page = await collection.get({
      where: { doc_id: docId },
      limit: pageSize,
      offset,
      include: ['metadatas'],
    });
    ids.push(...page.ids);
    if (page.ids.length < pageSize) break;
  }
  return ids;
}

async function removeOldChunks(collection, docId, keepPrefix) {
  const ids = await idsForDoc(collection, docId);
  const stale = ids.filter((id) => !id.startsWith(`${keepPrefix}__`));
  for (const batch of batches(stale, ID_BATCH)) {
    await collection.delete({ ids: batch });
  }
  return stale.length;
}

export async function stageDocument({ collectionId, title, content, contentHash, chunks }) {
  const meta = await getCollectionMeta(collectionId);
  if (!meta) throw new Error('集合不存在');
  const collection = await getSeekdbCollection(meta);

  const started = performance.now();
  const normalizedTitle = title.trim().toLowerCase().replace(/\s+/g, ' ');
  const docId = `doc_${crypto.createHash('sha256').update(normalizedTitle).digest('hex').slice(0, 16)}`;
  const token = crypto.randomBytes(6).toString('hex');
  const prefix = `${docId}__${token}`;
  const ids = toIdList(chunks.length, prefix);
  const metadatas = chunks.map((chunk, index) => ({
    doc_id: docId,
    title,
    chunk_index: index,
  }));

  const addStarted = performance.now();
  for (const batch of batches(chunks.map((_, index) => index), ADD_BATCH)) {
    await collection.add({
      ids: batch.map((index) => ids[index]),
      documents: batch.map((index) => chunks[index].text),
      metadatas: batch.map((index) => metadatas[index]),
      embeddings: batch.map((index) => chunks[index].embedding),
    });
  }
  const addMs = performance.now() - addStarted;

  let cleanupMs = 0;
  let removedChunks = 0;
  try {
    const cleanupStarted = performance.now();
    removedChunks = await removeOldChunks(collection, docId, prefix);
    cleanupMs = performance.now() - cleanupStarted;
  } catch (error) {
    await Promise.all(
      batches(ids, ID_BATCH).map((batch) => collection.delete({ ids: batch }).catch(() => {})),
    );
    throw error;
  }

  const importedAt = Date.now();
  await upsertDocument(collectionId, {
    docId,
    title,
    contentHash,
    charCount: content.length,
    chunkCount: chunks.length,
    chunkPrefix: prefix,
    importedAt,
  });
  await markImport(collectionId, importedAt);

  return {
    docId,
    title,
    chunkCount: chunks.length,
    removedChunks,
    chunkPrefix: prefix,
    timings: {
      addMs: Math.round(addMs),
      cleanupMs: Math.round(cleanupMs),
      totalMs: Math.round(performance.now() - started),
    },
  };
}

async function verifySearchable(collection, doc) {
  const ids = toIdList(doc.chunkCount, doc.chunkPrefix);
  const first = await collection.get({
    ids: [ids[0]],
    include: ['documents', 'embeddings'],
  });
  const sampleText = first.documents?.[0] ?? '';
  const sampleVector = first.embeddings?.[0] ?? null;

  const candidates = [probeSnippet(sampleText, 24), sanitizeQuery(doc.title, 40)].filter(Boolean);
  let fulltextHit = false;
  let fulltextProbe = '';
  for (const query of candidates) {
    const result = await collection.get({
      whereDocument: { $contains: query },
      limit: 10,
      include: ['metadatas'],
    });
    if (result.ids.some((id) => id.startsWith(`${doc.chunkPrefix}__`))) {
      fulltextHit = true;
      fulltextProbe = query;
      break;
    }
  }

  let vectorHit = false;
  let vectorDistance = null;
  if (sampleVector) {
    const result = await collection.query({
      queryEmbeddings: [sampleVector],
      nResults: 10,
      include: ['metadatas', 'distances'],
    });
    const position = result.ids[0].findIndex((id) => id.startsWith(`${doc.chunkPrefix}__`));
    vectorHit = position >= 0;
    if (position >= 0) vectorDistance = result.distances?.[0]?.[position] ?? null;
  }

  return {
    docId: doc.docId,
    title: doc.title,
    fulltextHit,
    fulltextProbe,
    vectorHit,
    vectorDistance,
    probeAvailable: Boolean(sampleText || sampleVector),
  };
}

export async function refreshCollection(collectionId) {
  const meta = await getCollectionMeta(collectionId);
  if (!meta) throw new Error('集合不存在');
  const collection = await getSeekdbCollection(meta);

  const refreshStarted = performance.now();
  await collection.refresh_index();
  let refreshMs = performance.now() - refreshStarted;

  let verification = null;
  const latest = await getLatestDocument(collectionId);
  if (latest) {
    verification = await verifySearchable(collection, latest);
    if (!verification.fulltextHit && verification.probeAvailable) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      await collection.refresh_index();
      refreshMs = performance.now() - refreshStarted;
      verification = await verifySearchable(collection, latest);
    }
  }

  const storedChunks = await collection.count();
  const [[counts]] = await getPool().query(
    `SELECT COUNT(*) AS docs, COALESCE(SUM(chunk_count), 0) AS chunks
       FROM stepfun_documents WHERE collection_id = ?`,
    [collectionId],
  );
  const expectedChunks = Number(counts.chunks);
  const verified = verification ? verification.fulltextHit || verification.vectorHit : true;

  await refreshIndexState(collectionId, {
    importAt: latest?.importedAt || 0,
    refreshAt: Date.now(),
    refreshMs: Math.round(refreshMs),
    verified,
  });

  return {
    refreshMs: Math.round(refreshMs),
    verified,
    docCount: Number(counts.docs),
    chunkCount: expectedChunks,
    storedChunks,
    countsMatch: storedChunks === expectedChunks,
    verification,
  };
}

export async function deleteDocument(collectionId, docId) {
  const meta = await getCollectionMeta(collectionId);
  if (!meta) throw new Error('集合不存在');
  const doc = await getDocument(collectionId, docId);
  if (!doc) throw new Error('文档不存在');
  const collection = await getSeekdbCollection(meta);
  const ids = await idsForDoc(collection, docId);
  for (const batch of batches(ids, ID_BATCH)) {
    await collection.delete({ ids: batch });
  }
  await deleteDocumentRow(collectionId, docId);
  return { docId, deletedChunks: ids.length };
}
