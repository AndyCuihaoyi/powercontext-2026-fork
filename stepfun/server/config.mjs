import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

export const ROOT = path.resolve(here, '..');

export const config = {
  host: process.env.HOST || '127.0.0.1',
  port: Number(process.env.PORT || 8797),
  distDir: path.join(ROOT, 'dist'),
  seekdb: {
    host: process.env.SEEKDB_HOST || '127.0.0.1',
    port: Number(process.env.SEEKDB_PORT || 2887),
    user: process.env.SEEKDB_USER || 'root',
    password: process.env.SEEKDB_PASSWORD || '',
    database: process.env.SEEKDB_DATABASE || 'stepfun_kb',
  },
  model: {
    id: 'bge-small-zh-v1.5',
    upstream: 'BAAI/bge-small-zh-v1.5',
    onnxRepo: 'Xenova/bge-small-zh-v1.5',
    revision: '75c43b069aac4d136ba6bc1122f995fedcfd2781',
    dimension: 512,
  },
  hybrid: {
    rankConstant: 60,
    candidateMultiplier: 4,
    candidateFloor: 20,
    candidateCap: 100,
    defaultTopK: 8,
  },
};
