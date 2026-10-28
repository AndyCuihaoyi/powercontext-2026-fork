import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import fsSync from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const BASE = process.env.STEPFUN_URL || 'http://127.0.0.1:8797';
export const EVIDENCE_DIR = path.join(ROOT, 'evidence');

// Prefer Playwright's full Chromium over the headless shell, which has no WebGPU.
function resolveChromePath() {
  if (process.env.CHROME_PATH) return process.env.CHROME_PATH;
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(os.homedir(), '.cache', 'ms-playwright');
  try {
    const builds = fsSync
      .readdirSync(cache)
      .filter((name) => /^chromium-\d+$/.test(name))
      .sort((a, b) => Number(b.slice('chromium-'.length)) - Number(a.slice('chromium-'.length)));
    for (const build of builds) {
      const executable = path.join(cache, build, 'chrome-linux', 'chrome');
      if (fsSync.existsSync(executable)) return executable;
    }
  } catch {
    // Fall through to Playwright's bundled default.
  }
  return undefined;
}

export const CHROME_PATH = resolveChromePath();

export function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function newTag() {
  return Date.now().toString(36).slice(-6);
}

export async function ensureEvidenceDir() {
  await fs.mkdir(EVIDENCE_DIR, { recursive: true });
}

export async function launchBrowser() {
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--enable-unsafe-webgpu',
      '--ignore-gpu-blocklist',
      '--enable-webgpu-developer-features',
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1,
    locale: 'zh-CN',
  });
  const page = await context.newPage();
  page.setDefaultTimeout(120_000);
  return { browser, context, page };
}

export function trackExternalRequests(page) {
  const external = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!/^https?:/i.test(url)) return;
    if (/^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/i.test(url)) return;
    external.push(url);
  });
  return external;
}

export function trackConsole(page) {
  const messages = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    // ONNX Runtime prints native warnings through console.error; keep them out of the failure list.
    if (/\[W:onnxruntime/.test(text)) return;
    messages.push(text);
  });
  page.on('pageerror', (error) => messages.push(String(error)));
  return messages;
}

export async function waitReady(page, timeout = 240_000) {
  await page.waitForFunction(() => Boolean(window.__stepfun), null, { timeout: 60_000, polling: 250 });
  await page.waitForFunction(
    () => {
      const snapshot = window.__stepfun?.state?.();
      return snapshot && (snapshot.embedderState === 'ready' || snapshot.embedderState === 'error');
    },
    null,
    { timeout, polling: 500 },
  );
  const snapshot = await page.evaluate(() => window.__stepfun.state());
  if (snapshot.embedderState !== 'ready') {
    const notice = await page.locator('#notice').textContent().catch(() => '');
    throw new Error(`本地模型加载失败：${notice || 'unknown'}`);
  }
  return snapshot;
}

export async function apiJson(pathname, init) {
  const response = await fetch(`${BASE}${pathname}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  const text = await response.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) throw new Error(`API ${pathname} 失败（HTTP ${response.status}）：${body?.error || text}`);
  return body;
}

export async function screenshot(page, filename) {
  await ensureEvidenceDir();
  await page.screenshot({ path: path.join(EVIDENCE_DIR, filename), fullPage: true });
}

export class Report {
  constructor(name, meta = {}) {
    this.file = `${name}.json`;
    this.data = {
      name,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      status: 'running',
      meta,
      steps: [],
      checks: [],
      consoleErrors: [],
      externalRequests: [],
    };
  }

  async step(name, fn) {
    const started = Date.now();
    try {
      const detail = await fn();
      this.data.steps.push({ name, status: 'passed', ms: Date.now() - started, detail: detail ?? null });
      console.log(`  ✓ ${name} (${Date.now() - started} ms)`);
      return detail;
    } catch (error) {
      this.data.steps.push({
        name,
        status: 'failed',
        ms: Date.now() - started,
        error: String(error?.message || error),
      });
      console.error(`  ✗ ${name}: ${error?.message || error}`);
      throw error;
    }
  }

  check(name, ok, detail) {
    this.data.checks.push({ name, ok: Boolean(ok), detail: detail ?? null });
    if (!ok) throw new Error(`检查失败：${name}${detail ? ` · ${detail}` : ''}`);
    console.log(`  ✓ 检查 ${name}${detail ? `：${detail}` : ''}`);
  }

  async save() {
    this.data.finishedAt = new Date().toISOString();
    await ensureEvidenceDir();
    await fs.writeFile(path.join(EVIDENCE_DIR, this.file), `${JSON.stringify(this.data, null, 2)}\n`);
    console.log(`报告已写入 evidence/${this.file}`);
  }
}
