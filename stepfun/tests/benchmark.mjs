import fs from 'node:fs/promises';
import path from 'node:path';
import {
  BASE,
  EVIDENCE_DIR,
  Report,
  apiJson,
  assert,
  ensureEvidenceDir,
  launchBrowser,
  screenshot,
  waitReady,
} from './lib/common.mjs';

const defaultKeys = ['wasm-fp32', 'wasm-q8', 'webgpu-fp16', 'webgpu-q8'];
const keys = (process.env.BENCH_VARIANTS || defaultKeys.join(','))
  .split(',')
  .map((key) => key.trim())
  .filter(Boolean);

const report = new Report('benchmark-report', { baseUrl: BASE, variants: keys });
let browser;

function formatMs(value) {
  if (value == null) return '—';
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`;
}

try {
  const launched = await launchBrowser();
  browser = launched.browser;
  const { page } = launched;

  let runtime = null;
  await report.step('准备应用与默认推理链路', async () => {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    runtime = await waitReady(page);
    await page.click('.tab[data-tab="bench"]');
    await screenshot(page, 'bench-01-panel.png');
    return { backend: runtime.embedder?.label, webgpuDetected: runtime.embedder?.webgpuDetected };
  });

  let result = null;
  await report.step(`运行基准变体：${keys.join(' / ')}`, async () => {
    result = await page.evaluate((variantKeys) => window.__stepfun.benchmark(variantKeys), keys);
    assert(result, '基准测试未返回结果');
    await ensureEvidenceDir();
    await fs.writeFile(path.join(EVIDENCE_DIR, 'benchmark.json'), `${JSON.stringify(result, null, 2)}\n`);
    return { variants: result.variants.map((variant) => ({ key: variant.key, status: variant.status })) };
  });

  await report.step('校验基准结果完整性', async () => {
    assert(result.variants.length === keys.length, `变体数量不符：${result.variants.length}/${keys.length}`);
    const ok = result.variants.filter((variant) => variant.status === 'ok');
    assert(ok.length > 0, '没有任何基准变体成功');
    for (const variant of ok) {
      assert(variant.quality?.evaluatedQueries === 22, `${variant.key} 评估查询数量异常`);
      assert(variant.docCount === 24, `${variant.key} 文档数量异常`);
      assert(variant.chunkCount > 0, `${variant.key} 分块数量异常`);
      assert(variant.modelBytes > 0, `${variant.key} 模型体积缺失`);
      assert(variant.e2eMs?.median > 0, `${variant.key} 端到端延迟缺失`);
    }
    const fp32 = ok.find((variant) => variant.key === 'wasm-fp32');
    const int8 = ok.find((variant) => variant.key === 'wasm-q8');
    if (fp32 && int8) {
      const compression = fp32.modelBytes / int8.modelBytes;
      report.check('INT8 模型显著压缩', compression > 3, `${compression.toFixed(2)}×`);
      report.check(
        'INT8 质量未大幅退化',
        (int8.quality?.recall10 ?? 0) >= (fp32.quality?.recall10 ?? 0) - 0.08,
        `Recall@10 ${fp32.quality?.recall10} → ${int8.quality?.recall10}`,
      );
    }
    const fp16 = result.variants.find((variant) => variant.key === 'webgpu-fp16');
    if (fp16) {
      report.check(
        'FP16 变体有明确结果（成功或带原因的失败）',
        fp16.status === 'ok' || Boolean(fp16.error),
        fp16.status === 'ok' ? '成功' : fp16.error,
      );
    }
    const leftovers = (await apiJson('/api/collections')).collections.filter((collection) => collection.name.startsWith('基准-'));
    report.check('临时基准集合已清理', leftovers.length === 0, `${leftovers.length} 个残留`);
    return {
      ok: ok.map((variant) => variant.key),
      failed: result.variants.filter((variant) => variant.status !== 'ok').map((variant) => `${variant.key}: ${variant.error}`),
    };
  });

  await report.step('保存基准界面截图', async () => {
    await page.click('.tab[data-tab="bench"]').catch(() => {});
    await page.waitForTimeout(500);
    await screenshot(page, 'bench-02-results.png');
    return { screenshot: 'evidence/bench-02-results.png' };
  });

  console.log('\n基准摘要');
  for (const variant of result.variants) {
    if (variant.status !== 'ok') {
      console.log(`- ${variant.label}: 失败（${variant.error}）`);
      continue;
    }
    const quality = variant.quality;
    console.log(
      `- ${variant.label}: ${(variant.modelBytes / 1024 / 1024).toFixed(1)} MiB · ${variant.compressionRatio?.toFixed(2)}× · ` +
        `R@5 ${quality?.recall5.toFixed(3)} · R@10 ${quality?.recall10.toFixed(3)} · nDCG@10 ${quality?.ndcg10.toFixed(3)} · ` +
        `查询向量化 ${formatMs(variant.queryEmbedMs?.median)} · seekdb ${formatMs(variant.searchMs?.median)} · 端到端 ${formatMs(variant.e2eMs?.median)}`,
    );
  }

  report.data.status = 'passed';
} catch (error) {
  report.data.status = 'failed';
  report.data.error = String(error?.stack || error);
  console.error(`\n基准测试失败：${error?.message || error}`);
  process.exitCode = 1;
} finally {
  await report.save();
  if (browser) await browser.close();
}
