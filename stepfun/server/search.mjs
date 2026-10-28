import { config } from './config.mjs';
import { getCollectionMeta, getSeekdbCollection, upsertSession } from './db.mjs';
import { sanitizeQuery } from './text.mjs';

function validateEmbedding(vector) {
  if (!Array.isArray(vector) || vector.length !== config.model.dimension) {
    throw new Error(`查询向量维度必须为 ${config.model.dimension}`);
  }
  let norm = 0;
  for (const value of vector) {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('查询向量包含非法数值');
    norm += value * value;
  }
  norm = Math.sqrt(norm);
  if (norm < 0.5 || norm > 1.5) throw new Error('查询向量未归一化');
}

export async function runSearch({ collectionId, query, embedding, topK, sessionId }) {
  const text = String(query ?? '').trim();
  if (!text) throw new Error('请输入查询内容');
  if (text.length > 500) throw new Error('查询不能超过 500 个字符');
  validateEmbedding(embedding);

  const meta = await getCollectionMeta(collectionId);
  if (!meta) throw new Error('集合不存在');
  const collection = await getSeekdbCollection(meta);

  const limit = Math.min(20, Math.max(1, Number(topK) || config.hybrid.defaultTopK));
  const sanitized = sanitizeQuery(text, 120);
  if (!sanitized) throw new Error('查询需包含文字或数字');
  const candidateK = Math.min(
    config.hybrid.candidateCap,
    Math.max(limit * config.hybrid.candidateMultiplier, config.hybrid.candidateFloor),
  );

  const started = performance.now();
  const result = await collection.hybridSearch({
    query: { whereDocument: { $contains: sanitized } },
    knn: { queryEmbeddings: [embedding], nResults: candidateK },
    rank: {
      rrf: {
        rankWindowSize: candidateK,
        rankConstant: config.hybrid.rankConstant,
      },
    },
    nResults: limit,
    include: ['documents', 'metadatas', 'distances'],
  });
  const searchMs = performance.now() - started;

  const ids = result.ids?.[0] ?? [];
  const documents = result.documents?.[0] ?? [];
  const metadatas = result.metadatas?.[0] ?? [];
  const distances = result.distances?.[0] ?? [];

  const results = ids.map((id, index) => {
    const metaEntry = metadatas[index] || {};
    return {
      chunkId: id,
      docId: metaEntry.doc_id ?? id.split('__')[0],
      title: metaEntry.title ?? '未命名文档',
      chunkIndex: Number(metaEntry.chunk_index ?? 0),
      text: documents[index] ?? '',
      distance: typeof distances[index] === 'number' ? distances[index] : null,
    };
  });

  if (sessionId) {
    await upsertSession({ sessionId, collectionId, lastQuery: text.slice(0, 500) });
  }

  return {
    results,
    searchMs: Math.round(searchMs * 10) / 10,
    candidateK,
    sanitizedQuery: sanitized,
    topK: limit,
    engine: 'seekdb',
    fusion: 'rrf',
  };
}
