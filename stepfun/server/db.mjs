import crypto from 'node:crypto';
import mysql from 'mysql2/promise';
import {
  SeekdbClient,
  Schema,
  FulltextIndexConfig,
  VectorIndexConfig,
} from 'seekdb';
import { config } from './config.mjs';

let pool = null;
let client = null;
const collectionCache = new Map();

const TABLES = [
  `CREATE TABLE IF NOT EXISTS stepfun_collections (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    seekdb_collection VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    dimension INT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE KEY uq_stepfun_collections_name (name)
  ) DEFAULT CHARSET=utf8mb4`,
  `CREATE TABLE IF NOT EXISTS stepfun_documents (
    collection_id VARCHAR(64) NOT NULL,
    doc_id VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_hash CHAR(64) NOT NULL,
    char_count INT NOT NULL,
    chunk_count INT NOT NULL,
    chunk_prefix VARCHAR(64) NOT NULL DEFAULT '',
    imported_at BIGINT NOT NULL,
    PRIMARY KEY (collection_id, doc_id),
    KEY idx_stepfun_documents_collection (collection_id)
  ) DEFAULT CHARSET=utf8mb4`,
  `CREATE TABLE IF NOT EXISTS stepfun_index_state (
    collection_id VARCHAR(64) NOT NULL PRIMARY KEY,
    doc_count INT NOT NULL DEFAULT 0,
    chunk_count INT NOT NULL DEFAULT 0,
    last_import_at BIGINT NOT NULL DEFAULT 0,
    last_refresh_at BIGINT NOT NULL DEFAULT 0,
    refresh_ms INT NOT NULL DEFAULT 0,
    verified TINYINT NOT NULL DEFAULT 0
  ) DEFAULT CHARSET=utf8mb4`,
  `CREATE TABLE IF NOT EXISTS stepfun_sessions (
    session_id VARCHAR(64) NOT NULL PRIMARY KEY,
    collection_id VARCHAR(64) NULL,
    backend VARCHAR(16) NULL,
    dtype VARCHAR(16) NULL,
    last_query VARCHAR(512) NULL,
    updated_at BIGINT NOT NULL
  ) DEFAULT CHARSET=utf8mb4`,
];

export function getPool() {
  if (!pool) throw new Error('database not initialized');
  return pool;
}

export function getClient() {
  if (!client) throw new Error('seekdb client not initialized');
  return client;
}

export async function initDb() {
  const { host, port, user, password, database } = config.seekdb;
  const admin = await mysql.createConnection({ host, port, user, password, charset: 'utf8mb4' });
  try {
    await admin.query(
      `CREATE DATABASE IF NOT EXISTS \`${database.replaceAll('`', '')}\` DEFAULT CHARACTER SET utf8mb4`,
    );
  } finally {
    await admin.end();
  }

  pool = mysql.createPool({
    host,
    port,
    user,
    password,
    database,
    charset: 'utf8mb4',
    connectionLimit: 8,
    waitForConnections: true,
  });

  for (const ddl of TABLES) await pool.query(ddl);

  const [prefixColumn] = await pool.query(
    `SELECT COUNT(*) AS n FROM information_schema.columns
      WHERE table_schema = DATABASE() AND table_name = 'stepfun_documents'
        AND column_name = 'chunk_prefix'`,
  );
  if (Number(prefixColumn[0].n) === 0) {
    await pool.query(
      `ALTER TABLE stepfun_documents ADD COLUMN chunk_prefix VARCHAR(64) NOT NULL DEFAULT ''`,
    );
  }

  client = new SeekdbClient({
    host,
    port,
    user,
    password,
    database,
    queryTimeout: 60_000,
  });
  // Triggers seekdb-js metadata-table bootstrap and verifies the connection.
  await client.listCollections();
  return { pool, client };
}

export async function closeDb() {
  collectionCache.clear();
  if (client) {
    await client.close().catch(() => {});
    client = null;
  }
  if (pool) {
    await pool.end().catch(() => {});
    pool = null;
  }
}

export function dimension() {
  return config.model.dimension;
}

export function collectionSchema() {
  return new Schema({
    fulltextIndex: new FulltextIndexConfig('ik', { ik_mode: 'smart' }),
    vectorIndex: new VectorIndexConfig({
      hnsw: { dimension: dimension(), distance: 'cosine' },
    }),
  });
}

export function slugifyTitle(title) {
  const normalized = title.trim().toLowerCase().replace(/\s+/g, ' ');
  return `doc_${crypto.createHash('sha256').update(normalized).digest('hex').slice(0, 16)}`;
}

export function seekdbCollectionName(id) {
  return `sf_${id}`;
}

export async function listCollections() {
  const [rows] = await pool.query(
    `SELECT c.id, c.name, c.seekdb_collection AS seekdbCollection, c.model, c.dimension,
            c.created_at AS createdAt, c.updated_at AS updatedAt,
            COALESCE(s.doc_count, 0) AS docCount, COALESCE(s.chunk_count, 0) AS chunkCount,
            COALESCE(s.last_refresh_at, 0) AS lastRefreshAt, COALESCE(s.verified, 0) AS verified
       FROM stepfun_collections c
       LEFT JOIN stepfun_index_state s ON s.collection_id = c.id
      ORDER BY c.created_at ASC`,
  );
  return rows;
}

export async function getCollectionMeta(id) {
  const [rows] = await pool.query(
    `SELECT id, name, seekdb_collection AS seekdbCollection, model, dimension,
            created_at AS createdAt, updated_at AS updatedAt
       FROM stepfun_collections WHERE id = ?`,
    [id],
  );
  return rows[0] || null;
}

export async function createCollection(rawName) {
  const name = String(rawName || '').trim();
  if (name.length < 1 || name.length > 40) throw new Error('集合名称需为 1–40 个字符');
  if (/[\u0000-\u001f\u007f]/.test(name)) throw new Error('集合名称包含非法字符');

  const id = `kb_${crypto.randomBytes(5).toString('hex')}`;
  const seekdbName = seekdbCollectionName(id);
  const now = Date.now();

  const [dupes] = await pool.query('SELECT id FROM stepfun_collections WHERE name = ?', [name]);
  if (dupes.length) throw new Error('同名集合已存在');

  await client.createCollection({
    name: seekdbName,
    schema: collectionSchema(),
    embeddingFunction: null,
  });
  try {
    await pool.execute(
      `INSERT INTO stepfun_collections (id, name, seekdb_collection, model, dimension, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
      [id, name, seekdbName, config.model.id, dimension(), now, now],
    );
    await pool.execute(
      `INSERT INTO stepfun_index_state (collection_id, doc_count, chunk_count, last_import_at, last_refresh_at, refresh_ms, verified)
       VALUES (?, 0, 0, 0, 0, 0, 0)`,
      [id],
    );
  } catch (error) {
    await client.deleteCollection(seekdbName).catch(() => {});
    throw error;
  }
  return getCollectionMeta(id);
}

export async function deleteCollection(id) {
  const meta = await getCollectionMeta(id);
  if (!meta) throw new Error('集合不存在');
  collectionCache.delete(id);
  await client.deleteCollection(meta.seekdbCollection).catch((error) => {
    if (!/not.*found|does not exist/i.test(String(error))) throw error;
  });
  await pool.execute('DELETE FROM stepfun_documents WHERE collection_id = ?', [id]);
  await pool.execute('DELETE FROM stepfun_index_state WHERE collection_id = ?', [id]);
  await pool.execute('DELETE FROM stepfun_collections WHERE id = ?', [id]);
}

export async function getSeekdbCollection(meta) {
  if (!meta) throw new Error('集合不存在');
  if (collectionCache.has(meta.id)) return collectionCache.get(meta.id);
  const collection = await client.getCollection({
    name: meta.seekdbCollection,
    embeddingFunction: null,
  });
  collectionCache.set(meta.id, collection);
  return collection;
}

export async function listDocuments(collectionId) {
  const [rows] = await pool.query(
    `SELECT doc_id AS docId, title, content_hash AS contentHash, char_count AS charCount,
            chunk_count AS chunkCount, chunk_prefix AS chunkPrefix, imported_at AS importedAt
       FROM stepfun_documents WHERE collection_id = ? ORDER BY imported_at ASC`,
    [collectionId],
  );
  return rows;
}

export async function getDocument(collectionId, docId) {
  const [rows] = await pool.query(
    `SELECT doc_id AS docId, title, content_hash AS contentHash, char_count AS charCount,
            chunk_count AS chunkCount, chunk_prefix AS chunkPrefix, imported_at AS importedAt
       FROM stepfun_documents WHERE collection_id = ? AND doc_id = ?`,
    [collectionId, docId],
  );
  return rows[0] || null;
}

export async function getLatestDocument(collectionId) {
  const [rows] = await pool.query(
    `SELECT doc_id AS docId, title, content_hash AS contentHash, char_count AS charCount,
            chunk_count AS chunkCount, chunk_prefix AS chunkPrefix, imported_at AS importedAt
       FROM stepfun_documents WHERE collection_id = ? ORDER BY imported_at DESC LIMIT 1`,
    [collectionId],
  );
  return rows[0] || null;
}

export async function upsertDocument(collectionId, doc) {
  await pool.execute(
    `INSERT INTO stepfun_documents
       (collection_id, doc_id, title, content_hash, char_count, chunk_count, chunk_prefix, imported_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       title = VALUES(title), content_hash = VALUES(content_hash), char_count = VALUES(char_count),
       chunk_count = VALUES(chunk_count), chunk_prefix = VALUES(chunk_prefix),
       imported_at = VALUES(imported_at)`,
    [
      collectionId,
      doc.docId,
      doc.title,
      doc.contentHash,
      doc.charCount,
      doc.chunkCount,
      doc.chunkPrefix,
      doc.importedAt,
    ],
  );
}

export async function deleteDocumentRow(collectionId, docId) {
  await pool.execute('DELETE FROM stepfun_documents WHERE collection_id = ? AND doc_id = ?', [
    collectionId,
    docId,
  ]);
}

export async function getIndexState(collectionId) {
  const [rows] = await pool.query(
    `SELECT doc_count AS docCount, chunk_count AS chunkCount, last_import_at AS lastImportAt,
            last_refresh_at AS lastRefreshAt, refresh_ms AS refreshMs, verified
       FROM stepfun_index_state WHERE collection_id = ?`,
    [collectionId],
  );
  return rows[0] || null;
}

export async function markImport(collectionId, importAt) {
  const [[counts]] = await pool.query(
    `SELECT COUNT(*) AS docs, COALESCE(SUM(chunk_count), 0) AS chunks
       FROM stepfun_documents WHERE collection_id = ?`,
    [collectionId],
  );
  await pool.execute(
    `INSERT INTO stepfun_index_state
       (collection_id, doc_count, chunk_count, last_import_at, last_refresh_at, refresh_ms, verified)
     VALUES (?, ?, ?, ?, 0, 0, 0)
     ON DUPLICATE KEY UPDATE
       doc_count = VALUES(doc_count), chunk_count = VALUES(chunk_count),
       last_import_at = GREATEST(last_import_at, VALUES(last_import_at)),
       verified = 0`,
    [collectionId, Number(counts.docs), Number(counts.chunks), importAt || 0],
  );
}

export async function refreshIndexState(collectionId, { importAt, refreshAt, refreshMs, verified }) {  const [[counts]] = await pool.query(
    `SELECT COUNT(*) AS docs, COALESCE(SUM(chunk_count), 0) AS chunks
       FROM stepfun_documents WHERE collection_id = ?`,
    [collectionId],
  );
  await pool.execute(
    `INSERT INTO stepfun_index_state
       (collection_id, doc_count, chunk_count, last_import_at, last_refresh_at, refresh_ms, verified)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       doc_count = VALUES(doc_count), chunk_count = VALUES(chunk_count),
       last_import_at = GREATEST(last_import_at, VALUES(last_import_at)),
       last_refresh_at = VALUES(last_refresh_at), refresh_ms = VALUES(refresh_ms),
       verified = VALUES(verified)`,
    [
      collectionId,
      Number(counts.docs),
      Number(counts.chunks),
      importAt || 0,
      refreshAt || 0,
      refreshMs || 0,
      verified ? 1 : 0,
    ],
  );
}

export async function getSession(sessionId) {
  const [rows] = await pool.query(
    `SELECT session_id AS sessionId, collection_id AS collectionId, backend, dtype,
            last_query AS lastQuery, updated_at AS updatedAt
       FROM stepfun_sessions WHERE session_id = ?`,
    [sessionId],
  );
  return rows[0] || null;
}

export async function upsertSession({ sessionId, collectionId, backend, dtype, lastQuery }) {
  // seekdb returns 9747 (malformed ps packet) for binary-protocol NULL bindings, so use text protocol here.
  await pool.query(
    `INSERT INTO stepfun_sessions (session_id, collection_id, backend, dtype, last_query, updated_at)
     VALUES (?, ?, ?, ?, ?, ?)
     ON DUPLICATE KEY UPDATE
       collection_id = COALESCE(VALUES(collection_id), collection_id),
       backend = COALESCE(VALUES(backend), backend),
       dtype = COALESCE(VALUES(dtype), dtype),
       last_query = COALESCE(VALUES(last_query), last_query),
       updated_at = VALUES(updated_at)`,
    [sessionId, collectionId || null, backend || null, dtype || null, lastQuery || null, Date.now()],
  );
}

export async function dbHealth() {
  const [[row]] = await pool.query('SELECT VERSION() AS version, DATABASE() AS db');
  const [tables] = await pool.query(
    `SELECT COUNT(*) AS n FROM information_schema.tables
      WHERE table_schema = DATABASE() AND table_name LIKE 'stepfun_%'`,
  );
  const [collections] = await pool.query('SELECT COUNT(*) AS n FROM stepfun_collections');
  return {
    version: row.version,
    database: row.db,
    metadataTables: Number(tables[0].n),
    collections: Number(collections[0].n),
  };
}
