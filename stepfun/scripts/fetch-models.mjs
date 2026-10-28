#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { ROOT } from '../server/config.mjs';

const lock = JSON.parse(await fsp.readFile(path.join(ROOT, 'models.lock.json'), 'utf8'));
const destDir = path.join(ROOT, 'public', 'models', 'bge-small-zh-v1.5');
const endpoints = [
  process.env.HF_ENDPOINT,
  'https://hf-mirror.com',
  'https://huggingface.co',
].filter(Boolean);

async function sha256(file) {
  const hash = crypto.createHash('sha256');
  await pipeline(fs.createReadStream(file), hash);
  return hash.digest('hex');
}

async function download(url, target) {
  const response = await fetch(url, { redirect: 'follow' });
  if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
  await fsp.mkdir(path.dirname(target), { recursive: true });
  const temp = `${target}.part`;
  await pipeline(Readable.fromWeb(response.body), fs.createWriteStream(temp));
  return temp;
}

let downloaded = 0;
let skipped = 0;
for (const [relative, meta] of Object.entries(lock.files)) {
  const target = path.join(destDir, relative);
  try {
    const stat = await fsp.stat(target);
    if (stat.size === meta.bytes && (await sha256(target)) === meta.sha256) {
      console.log(`✓ ${relative}（已存在）`);
      skipped += 1;
      continue;
    }
  } catch {
    /* missing */
  }

  let lastError = null;
  for (const endpoint of endpoints) {
    const url = `${endpoint}/${lock.model}/resolve/${lock.revision}/${relative}`;
    try {
      const temp = await download(url, target);
      const actual = await sha256(temp);
      if (actual !== meta.sha256) throw new Error(`sha256 不匹配（${actual.slice(0, 12)}…）`);
      await fsp.rename(temp, target);
      console.log(`↓ ${relative}（${(meta.bytes / 1024 / 1024).toFixed(1)} MiB，${endpoint}）`);
      lastError = null;
      downloaded += 1;
      break;
    } catch (error) {
      lastError = error;
      await fsp.rm(`${target}.part`, { force: true }).catch(() => {});
      console.warn(`  ${endpoint} 失败：${error.message}`);
    }
  }
  if (lastError) {
    console.error(`✗ ${relative} 下载失败`);
    process.exitCode = 1;
    break;
  }
}

if (!process.exitCode) {
  const total = Object.values(lock.files).reduce((sum, file) => sum + file.bytes, 0);
  console.log(`模型就绪：${path.relative(ROOT, destDir)}（${(total / 1024 / 1024).toFixed(1)} MiB，revision ${lock.revision.slice(0, 8)}）`);
  console.log(`新下载 ${downloaded} 个文件，跳过 ${skipped} 个`);
}
