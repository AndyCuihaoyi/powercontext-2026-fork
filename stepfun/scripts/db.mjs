#!/usr/bin/env node
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import mysql from 'mysql2/promise';
import { config, ROOT } from '../server/config.mjs';

const dataRoot = process.env.STEPFUN_DATA || path.join(ROOT, '.seekdb');
const instanceDir = path.join(dataRoot, 'instance');
const storeDir = path.join(dataRoot, 'store');
const pidFile = path.join(dataRoot, 'seekdb.pid');
const logFile = path.join(dataRoot, 'seekdb.log');

function whichBinary() {
  const candidates = [
    process.env.SEEKDB_BIN,
    path.join(dataRoot, 'bin', 'seekdb'),
    '/usr/local/bin/seekdb',
    '/usr/bin/seekdb',
  ].filter(Boolean);
  for (const candidate of candidates) {
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      /* keep looking */
    }
  }
  try {
    return execFileSync('which', ['seekdb'], { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

async function connect() {
  return mysql.createConnection({
    host: config.seekdb.host,
    port: config.seekdb.port,
    user: config.seekdb.user,
    password: config.seekdb.password,
    connectTimeout: 3000,
  });
}

async function ping() {
  let conn;
  try {
    conn = await connect();
    const [[row]] = await conn.query('SELECT VERSION() AS version');
    return { up: true, version: row.version };
  } catch {
    return { up: false, version: null };
  } finally {
    if (conn) await conn.end().catch(() => {});
  }
}

function readPid() {
  try {
    const pid = Number(fs.readFileSync(pidFile, 'utf8').trim());
    if (!Number.isInteger(pid) || pid <= 0) return null;
    process.kill(pid, 0);
    return pid;
  } catch {
    return null;
  }
}

async function logTail(lines = 20) {
  try {
    const text = await fsp.readFile(logFile, 'utf8');
    return text.trim().split('\n').slice(-lines).join('\n');
  } catch {
    return '(no log yet)';
  }
}

async function start() {
  const current = await ping();
  if (current.up) {
    console.log(`seekdb 已在 ${config.seekdb.host}:${config.seekdb.port} 运行（${current.version}）`);
    return;
  }
  const binary = whichBinary();
  if (!binary) {
    console.error('未找到 seekdb 可执行文件。请安装 seekdb 或用 SEEKDB_BIN=/path/to/seekdb 指定。');
    process.exit(1);
  }
  await fsp.mkdir(instanceDir, { recursive: true });
  await fsp.mkdir(storeDir, { recursive: true });
  const logFd = fs.openSync(logFile, 'a');
  const args = [
    '--nodaemon',
    `--base-dir=${instanceDir}`,
    `--port=${config.seekdb.port}`,
    `--data-dir=${storeDir}`,
    `--redo-dir=${path.join(storeDir, 'redo')}`,
    '--parameter', 'memory_limit=2G',
    '--parameter', 'datafile_size=2G',
    '--parameter', 'log_disk_size=2G',
  ];
  const child = spawn(binary, args, { detached: true, stdio: ['ignore', logFd, logFd] });
  child.unref();
  fs.writeFileSync(pidFile, String(child.pid));
  console.log(`启动 seekdb（pid ${child.pid}，data ${path.relative(ROOT, storeDir)}）...`);

  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const status = await ping();
    if (status.up) {
      console.log(`seekdb 就绪：${status.version} @ ${config.seekdb.host}:${config.seekdb.port}`);
      return;
    }
    if (child.exitCode !== null) {
      console.error(`seekdb 启动后退出（code ${child.exitCode}）。日志：\n${await logTail()}`);
      process.exit(1);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  console.error(`seekdb 在 90 秒内未就绪。日志：\n${await logTail()}`);
  process.exit(1);
}

async function stop() {
  const current = await ping();
  const pid = readPid();
  if (!current.up && !pid) {
    console.log('seekdb 未在运行');
    return;
  }
  if (current.up) {
    try {
      const conn = await connect();
      await conn.query('SHUTDOWN').catch(() => {});
      await conn.end().catch(() => {});
    } catch {
      /* fall back to signalling */
    }
  }
  if (pid) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch {
      /* already gone */
    }
  } else if (current.up) {
    console.error('seekdb 在运行但缺少 pid 文件（可能是外部实例），请手动停止。');
    process.exit(1);
  }
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (!(await ping()).up) {
      try {
        await fsp.rm(pidFile, { force: true });
      } catch {
        /* ignore */
      }
      console.log('seekdb 已停止');
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  console.error('seekdb 30 秒内未停止，请检查进程。');
  process.exit(1);
}

async function status() {
  const current = await ping();
  if (!current.up) {
    console.log(`seekdb 未运行（${config.seekdb.host}:${config.seekdb.port}）`);
    process.exitCode = 1;
    return;
  }
  console.log(`seekdb 运行中：${current.version} @ ${config.seekdb.host}:${config.seekdb.port}`);
  let conn;
  try {
    conn = await connect();
    const [[db]] = await conn.query('SELECT COUNT(*) AS n FROM information_schema.schemata WHERE schema_name = ?', [
      config.seekdb.database,
    ]);
    console.log(`目标数据库 ${config.seekdb.database}: ${Number(db.n) > 0 ? '已创建' : '尚未创建'}`);
  } finally {
    if (conn) await conn.end().catch(() => {});
  }
}

async function init() {
  const { initDb, dbHealth, closeDb } = await import('../server/db.mjs');
  await initDb();
  const health = await dbHealth();
  console.log(`数据库就绪：${health.version} · ${health.database} · ${health.metadataTables} 张元数据表 · ${health.collections} 个集合`);
  await closeDb();
}

const command = process.argv[2] || 'status';
const actions = { start, stop, status, restart: async () => { await stop(); await start(); }, init };
if (!actions[command]) {
  console.error('用法: node scripts/db.mjs <start|stop|restart|status|init>');
  process.exit(1);
}
actions[command]().catch((error) => {
  console.error(error);
  process.exit(1);
});
