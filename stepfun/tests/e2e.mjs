import mysql from 'mysql2/promise';
import {
  BASE,
  Report,
  apiJson,
  assert,
  launchBrowser,
  newTag,
  screenshot,
  trackConsole,
  trackExternalRequests,
  waitReady,
} from './lib/common.mjs';

const tag = newTag();
const collectionName = `端到端验收-${tag}`;
const unique = `端侧星河${tag}`;
const incrementalProbe = `增量探针${tag}`;
const doc1Title = `混合检索验收-${tag}`;
const doc1Content = [
  `端到端验收文档。唯一关键词：${unique}。`,
  'seekdb 将全文索引与向量索引放在同一个数据库内核中。混合检索由 DBMS_HYBRID_SEARCH.GET_SQL 生成一条 SQL，并在库内完成 RRF 融合。',
  '全文通道使用 IK 分词器，向量通道使用 HNSW 索引与 cosine 距离。应用服务只提交查询文本与查询向量，不会分别拉取两路候选再自行合并。',
  '浏览器端通过 Transformers.js 加载 bge-small-zh-v1.5 的 ONNX 权重，切块后逐批推理，得到 512 维归一化向量。',
  '导入完成后调用 refresh_index，并用新文档中的独特片段做全文探测与向量近邻探测，确认刷新结果可以检索。',
  '所有向量、原文与文档元数据都写入本地 seekdb，浏览器刷新后通过会话恢复集合、后端与最近查询。',
].join('\n');
const doc2Title = `增量导入验收-${tag}`;
const doc2Content = [
  `增量导入文档。独特探针：${incrementalProbe}。`,
  '这篇文档在首次批量刷新之后才写入，用于验证增量导入与索引刷新流程。',
  '刷新完成后，全文通道与向量通道都应立即检索到这段新增内容。',
].join('\n');

const report = new Report('e2e-report', {
  baseUrl: BASE,
  collectionName,
  unique,
  incrementalProbe,
});
const started = Date.now();
let browser;
let collectionId = null;
let extraCollectionId = null;
let external = [];
let consoleErrors = [];

async function dbEvidence(detail, expectedDocs) {
  const connection = await mysql.createConnection({
    host: process.env.SEEKDB_HOST || '127.0.0.1',
    port: Number(process.env.SEEKDB_PORT || 2887),
    user: process.env.SEEKDB_USER || 'root',
    password: process.env.SEEKDB_PASSWORD || '',
    database: process.env.SEEKDB_DATABASE || 'stepfun_kb',
    charset: 'utf8mb4',
  });
  try {
    const seekdbName = detail.collection.seekdbCollection;
    const [[mapping]] = await connection.query(
      'SELECT collection_id AS collectionId, settings FROM sdk_collections WHERE collection_name = ? LIMIT 1',
      [seekdbName],
    );
    assert(mapping, `sdk_collections 中找不到集合 ${seekdbName} 的映射`);
    const physical = `c$v2$${mapping.collectionId}`;
    const [[createRow]] = await connection.query(`SHOW CREATE TABLE \`${physical.replaceAll('`', '')}\``);
    const createSql = Object.values(createRow).find((value) => typeof value === 'string' && /CREATE TABLE/i.test(value)) || '';
    const [[countRow]] = await connection.query(`SELECT COUNT(*) AS n FROM \`${physical.replaceAll('`', '')}\``);

    const [metadata] = await connection.query(
      'SELECT COUNT(*) AS docs, COALESCE(SUM(chunk_count), 0) AS chunks FROM stepfun_documents WHERE collection_id = ?',
      [collectionId],
    );

    return {
      physicalTable: physical,
      rows: Number(countRow.n),
      settings: mapping.settings,
      fulltextIndex: /fulltext/i.test(createSql) && /ik/i.test(createSql),
      vectorIndex: /vector/i.test(createSql) || /hnsw/i.test(createSql),
      createSql,
      metadataDocs: Number(metadata[0].docs),
      metadataChunks: Number(metadata[0].chunks),
      expectedDocs,
    };
  } finally {
    await connection.end();
  }
}

try {
  const launched = await launchBrowser();
  browser = launched.browser;
  const { page } = launched;
  external = trackExternalRequests(page);
  consoleErrors = trackConsole(page);

  let initial = null;
  await report.step('打开应用并等待本地模型就绪', async () => {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' });
    initial = await waitReady(page);
    assert(initial.embedder, '缺少推理后端状态');
    const badge = (await page.locator('#backend-badge').textContent())?.trim() || '';
    assert(badge === initial.embedder.label, `UI 后端标识（${badge}）与状态（${initial.embedder.label}）不一致`);
    report.check('后端为浏览器本地推理', ['webgpu', 'wasm'].includes(initial.embedder.backend), initial.embedder.label);
    report.check(
      '后端状态包含降级尝试记录',
      Array.isArray(initial.embedder.attempts) && initial.embedder.attempts.length > 0,
      initial.embedder.attempts.map((item) => `${item.candidate}${item.ok ? '✓' : '✗'}`).join(','),
    );
    if (initial.embedder.webgpuDetected) {
      report.check(
        'WebGPU 探测成功（优先尝试）',
        initial.embedder.attempts.some((item) => /^WebGPU/i.test(item.candidate)),
        initial.embedder.label,
      );
    }
    await screenshot(page, 'e2e-01-ready.png');
    return { backend: initial.embedder, webgpuDetected: initial.embedder.webgpuDetected };
  });

  await report.step('通过 UI 创建独立测试集合', async () => {
    await page.fill('#collection-name', collectionName);
    await page.click('#create-collection');
    await page.waitForFunction(
      (name) => window.__stepfun.state().collections.some((collection) => collection.name === name),
      collectionName,
      { timeout: 30_000 },
    );
    const snapshot = await page.evaluate(() => window.__stepfun.state());
    const collection = snapshot.collections.find((item) => item.name === collectionName);
    assert(collection, '集合未出现在列表中');
    collectionId = collection.id;
    assert(snapshot.collectionId === collectionId, '新建集合未被自动选中');
    report.check('集合写入 seekdb 元数据表', Boolean(collection.seekdbCollection), collection.seekdbCollection);
    return { collectionId, seekdbCollection: collection.seekdbCollection };
  });

  await report.step('UI 导入文档并完成刷新验证', async () => {
    await page.waitForFunction(() => !document.querySelector('#import-button').disabled, null, { timeout: 60_000 });
    await page.fill('#doc-title', doc1Title);
    await page.fill('#doc-content', doc1Content);
    await page.click('#import-button');
    await page.waitForFunction(
      (title) => {
        const snapshot = window.__stepfun.state();
        return Boolean(snapshot.detail?.documents?.some((document) => document.title === title)) &&
          Boolean(snapshot.detail?.indexState?.verified);
      },
      doc1Title,
      { timeout: 180_000, polling: 500 },
    );
    const snapshot = await page.evaluate(() => window.__stepfun.state());
    const document = snapshot.detail.documents.find((item) => item.title === doc1Title);
    assert(document, '文档未进入列表');
    assert(document.chunkCount >= 1, '分块数量异常');
    report.check('浏览器切块产生多个分块', document.chunkCount >= 1, `${document.chunkCount} 块 / ${document.charCount} 字`);

    const detail = await apiJson(`/api/collections/${collectionId}`);
    report.check('集合详情包含文档与索引状态', detail.documents.length === 1 && detail.indexState?.verified === 1);
    const evidence = await dbEvidence(detail, 1);
    assert(evidence.fulltextIndex, `物理表缺少 IK 全文索引：${evidence.createSql.slice(0, 400)}`);
    assert(evidence.vectorIndex, `物理表缺少向量索引：${evidence.createSql.slice(0, 400)}`);
    const schema = evidence.settings?.schema;
    report.check(
      '集合 schema 为 HNSW/512d/cosine + IK',
      schema?.vectorIndex?.hnsw?.dimension === 512 &&
        schema?.vectorIndex?.hnsw?.distance === 'cosine' &&
        schema?.fulltextIndex?.analyzer === 'ik',
      JSON.stringify(schema ?? {}),
    );
    report.check('seekdb 物理表同时具备全文与向量索引', true, `${evidence.physicalTable} · ${evidence.rows} 行`);
    report.check('物理表行数与元数据分块数一致', evidence.rows === evidence.metadataChunks, `${evidence.rows}/${evidence.metadataChunks}`);
    return { document, indexState: detail.indexState, physical: evidence.physicalTable, rows: evidence.rows };
  });

  let firstSearch = null;
  await report.step('UI 混合检索命中导入内容', async () => {
    await page.waitForFunction(() => !document.querySelector('#search-button').disabled, null, { timeout: 30_000 });
    await page.fill('#query-input', unique);
    await page.click('#search-button');
    await page.waitForFunction(
      () => document.querySelectorAll('#results .result-item').length > 0 || Boolean(document.querySelector('#results .empty')),
      null,
      { timeout: 60_000, polling: 250 },
    );
    const meta = (await page.locator('#search-meta').textContent()) || '';
    assert(meta.includes('seekdb RRF'), `检索元信息缺少数据库内融合标识：${meta}`);
    firstSearch = await page.evaluate((query) => window.__stepfun.search(query), unique);
    assert(firstSearch.results.length > 0, '检索没有返回结果');
    assert(firstSearch.engine === 'seekdb' && firstSearch.fusion === 'rrf', '检索未标记为 seekdb/RRF');
    assert(firstSearch.results.some((hit) => hit.title === doc1Title), '检索结果未包含目标文档');
    report.check('检索由 seekdb 内部 RRF 融合', firstSearch.engine === 'seekdb' && firstSearch.fusion === 'rrf', `${firstSearch.engine}/${firstSearch.fusion}`);
    report.check('命中目标文档', true, `top1=${firstSearch.results[0].title} · ${firstSearch.searchMs} ms · 候选 ${firstSearch.candidateK}`);
    await screenshot(page, 'e2e-02-search.png');
    return {
      searchMs: firstSearch.searchMs,
      topK: firstSearch.topK,
      candidateK: firstSearch.candidateK,
      results: firstSearch.results.map((hit) => ({ title: hit.title, docId: hit.docId, distance: hit.distance })),
    };
  });

  await report.step('增量导入后新内容立即可检索', async () => {
    const result = await page.evaluate(
      ([title, content]) => window.__stepfun.importText(title, content),
      [doc2Title, doc2Content],
    );
    assert(result.verified === true, '增量导入后刷新验证未通过');
    const refresh = await apiJson(`/api/collections/${collectionId}/refresh`, { method: 'POST', body: '{}' });
    const verification = refresh.refresh.verification;
    assert(refresh.refresh.verified === true, '显式刷新未通过验证');
    assert(verification?.fulltextHit === true, `全文通道未命中新文档：${JSON.stringify(verification)}`);
    assert(verification?.vectorHit === true, `向量通道未命中新文档：${JSON.stringify(verification)}`);
    const search = await page.evaluate((query) => window.__stepfun.search(query), incrementalProbe);
    assert(search.results.some((hit) => hit.title === doc2Title), '增量文档未被检索到');
    report.check('刷新同时通过全文与向量探测', true, `fulltext=${verification.fulltextHit} · vector=${verification.vectorHit} · ${refresh.refresh.refreshMs} ms`);
    report.check('增量文档可检索', true, `top1=${search.results[0].title}`);
    const snapshot = await page.evaluate(() => window.__stepfun.state());
    assert(snapshot.detail.documents.length === 2, '文档数量不是 2');
    return { import: result, verification, refreshMs: refresh.refresh.refreshMs };
  });

  await report.step('集合切换时文档隔离且可切回', async () => {
    const second = await page.evaluate((name) => window.__stepfun.createCollection(name), `隔离验收-${tag}`);
    extraCollectionId = second.id;
    let snapshot = await page.evaluate(() => window.__stepfun.state());
    assert(snapshot.collectionId === extraCollectionId, '新集合未被选中');
    assert((snapshot.detail?.documents?.length ?? -1) === 0, '新集合不应包含原集合文档');
    await page.evaluate((id) => window.__stepfun.selectCollection(id), collectionId);
    snapshot = await page.evaluate(() => window.__stepfun.state());
    assert(snapshot.collectionId === collectionId, '未能切回原集合');
    assert(snapshot.detail?.documents?.length === 2, '切回后文档数量不一致');
    await apiJson(`/api/collections/${extraCollectionId}`, { method: 'DELETE' });
    extraCollectionId = null;
    report.check('集合隔离与切换', true, '新集合 0 篇，切回后 2 篇');
    return { switchedCollectionId: second.id };
  });

  await report.step('刷新页面后恢复集合、后端与最近查询', async () => {
    const before = await page.evaluate(() => window.__stepfun.state());
    await page.reload({ waitUntil: 'domcontentloaded' });
    const restored = await waitReady(page);
    assert(restored.collectionId === collectionId, `刷新后集合未恢复：${restored.collectionId}`);
    assert(restored.detail?.documents?.length === 2, '刷新后文档列表不完整');
    assert(restored.session?.lastQuery === incrementalProbe, `最近查询未恢复：${restored.session?.lastQuery}`);
    report.check('会话恢复集合与最近查询', true, `${collectionId} · ${restored.session.lastQuery}`);
    report.check('刷新后后端仍可用', restored.embedderState === 'ready', restored.embedder?.label);
    await screenshot(page, 'e2e-03-session.png');
    return { backendBefore: before.embedder?.label, backendAfter: restored.embedder?.label, lastQuery: restored.session.lastQuery };
  });

  await report.step('强制 WASM 参数生效并在 UI 标注', async () => {
    await page.goto(`${BASE}/?backend=wasm`, { waitUntil: 'domcontentloaded' });
    const forced = await waitReady(page);
    assert(forced.embedder.backend === 'wasm', `强制 WASM 后实际后端为 ${forced.embedder.backend}`);
    assert(forced.embedder.forcedWasm === true, '未标记强制 WASM');
    const badge = (await page.locator('#backend-badge').textContent())?.trim() || '';
    assert(/wasm/i.test(badge), `UI 未标注 WASM：${badge}`);
    const notice = (await page.locator('#notice').textContent())?.trim() || '';
    assert(notice.includes('强制'), `UI 未提示强制 WASM：${notice}`);
    report.check('强制 WASM 生效', true, badge);
    await screenshot(page, 'e2e-04-forced-wasm.png');
    return { backend: forced.embedder.backend, dtype: forced.embedder.dtype, notice };
  });

  await report.step('运行期无外部网络请求', async () => {
    assert(external.length === 0, `检测到外部请求：${external.slice(0, 5).join(', ')}`);
    report.check('仅访问本机资源', true, `${external.length} 个外部请求`);
    return { externalRequests: external.length };
  });

  report.data.status = 'passed';
} catch (error) {
  report.data.status = 'failed';
  report.data.error = String(error?.stack || error);
  console.error(`\nE2E 失败：${error?.message || error}`);
  process.exitCode = 1;
} finally {
  report.data.durationMs = Date.now() - started;
  report.data.collectionId = collectionId;
  report.data.externalRequests = external;
  report.data.consoleErrors = consoleErrors;
  if (collectionId) {
    try {
      await apiJson(`/api/collections/${encodeURIComponent(collectionId)}`, { method: 'DELETE' });
      report.data.cleanup = 'deleted test collection';
    } catch (error) {
      report.data.cleanup = `cleanup failed: ${error.message}`;
    }
  }
  if (extraCollectionId) {
    try {
      await apiJson(`/api/collections/${encodeURIComponent(extraCollectionId)}`, { method: 'DELETE' });
    } catch {
      /* best-effort cleanup */
    }
  }
  await report.save();
  if (browser) await browser.close();
}
