#!/usr/bin/env node
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { ROOT } from '../server/config.mjs';

const src = path.join(ROOT, 'node_modules', 'onnxruntime-web', 'dist');
const dest = path.join(ROOT, 'public', 'ort');
const files = [
  'ort-wasm-simd-threaded.jsep.mjs',
  'ort-wasm-simd-threaded.jsep.wasm',
  'ort-wasm-simd-threaded.mjs',
  'ort-wasm-simd-threaded.wasm',
];

if (!fs.existsSync(src)) {
  console.error('onnxruntime-web 未安装，跳过 ORT 资源准备');
  process.exit(1);
}

await fsp.mkdir(dest, { recursive: true });
for (const name of files) {
  const from = path.join(src, name);
  const to = path.join(dest, name);
  try {
    const [a, b] = await Promise.all([fsp.stat(from), fsp.stat(to).catch(() => null)]);
    if (b && a.size === b.size && a.mtimeMs <= b.mtimeMs) continue;
    await fsp.copyFile(from, to);
    console.log(`copied public/ort/${name}`);
  } catch (error) {
    console.error(`复制 ${name} 失败：`, error.message);
    process.exitCode = 1;
  }
}
