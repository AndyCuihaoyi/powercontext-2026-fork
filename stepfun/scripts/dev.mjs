#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { ROOT } from '../server/config.mjs';

const viteBin = path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js');
if (!fs.existsSync(viteBin)) {
  console.error('未安装依赖：请先在 stepfun/ 目录运行 npm install');
  process.exit(1);
}

const colors = { api: '\u001b[36m', web: '\u001b[35m', reset: '\u001b[0m' };
const procs = [];

function run(name, args) {
  const child = spawn(process.execPath, args, {
    cwd: ROOT,
    env: { ...process.env, FORCE_COLOR: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const prefix = `${colors[name] || ''}[${name}]${colors.reset} `;
  const relay = (stream, target) => {
    let buffer = '';
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => {
      buffer += chunk;
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) target.write(prefix + line + '\n');
    });
    stream.on('end', () => {
      if (buffer) target.write(prefix + buffer + '\n');
    });
  };
  relay(child.stdout, process.stdout);
  relay(child.stderr, process.stderr);
  child.on('exit', (code) => {
    if (stopping) return;
    console.log(`${prefix}退出（code ${code}），停止其它进程`);
    shutdown(code ?? 0);
  });
  procs.push(child);
  return child;
}

let stopping = false;
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of procs) {
    if (child.exitCode === null) child.kill('SIGTERM');
  }
  setTimeout(() => process.exit(code), 400);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

run('api', ['server/index.mjs']);
run('web', [viteBin, '--host', '127.0.0.1', '--port', '5173']);
console.log(`开发模式：前端 http://127.0.0.1:5173 ｜ API http://127.0.0.1:${process.env.PORT || 8797}`);
