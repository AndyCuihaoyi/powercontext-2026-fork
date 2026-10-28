# 记忆当铺 · 源码态部署手册

本手册记录赛题验证时实际跑通的部署方式：**Dify 1.18.0 源码 + seekdb 1.4.0 + Redis + PowerContext 1.4.1 + 当铺网关**。
验证环境没有 Docker daemon，也没有用户命名空间，因此没有依赖 `dify-sandbox` / plugin daemon；
工作流只使用 Start / HTTP Request / If-Else / End 节点，这两者本来也不需要。

> 端口约定：Dify API `5001`、seekdb MySQL 协议 `2886`、Redis `56379`、PowerContext `17429`、当铺网关 `8099`。
> 全部组件只监听 `127.0.0.1`，不要把 API Key 与数据库口令带进仓库。

## 0. 目录

```
dify/
├── dsl/memory-pawnshop.yml       # 导入 Dify 的工作流 DSL
├── gateway/                      # 自定义后端：账本 + PowerContext + 模型代理 + 静态体验页
├── scripts/                      # 建库、导入发布、seekdb/PowerContext 验证
├── validation/run_e2e.py         # 通过 Dify Service API 跑完整玩家流程
├── web/index.html                # 体验页（由网关在 / 直接提供）
└── deploy/                       # 本手册与配置样例
```

## 1. seekdb

```bash
# 解压 seekdb 1.4.x 发行包后
cd dify/deploy
SEEKDB_HOME=/path/to/seekdb SEEKDB_BASE_DIR=/path/to/dify-runtime/seekdb ./seekdb-start.sh
```

初始化 Dify 元数据库、插件库与当铺账本：

```bash
cd dify
python3 -m venv gateway/.venv
gateway/.venv/bin/pip install -r gateway/requirements.txt
cp gateway/.env.example gateway/.env      # 按实际端口/口令修改
gateway/.venv/bin/python scripts/init_db.py   # 建 dify / dify_plugin / pawnshop，tickets 尝试 IK 全文索引
```

`init_db.py` 与 Dify 自带迁移都会在 seekdb 上验证；当铺账本表结构见 `scripts/init_db.sql`。

## 2. Redis 与 Dify API / Worker

Redis 7.x 以 `--port 56379 --requirepass <pwd>` 启动即可。

Dify 1.18.0 源码：

```bash
cd /path/to/dify-1.18.0/api
cp /path/to/dify/deploy/dify.env.example .env   # 再补 SECRET_KEY 等必填项
uv sync                                          # 或已准备好的 .venv
```

**seekdb 迁移注意点**：Dify 的 `5578e028b2f2` 迁移使用 `CREATE TEMPORARY TABLE`，seekdb 不支持。
在空库上该迁移没有数据可搬，可安全跳过：

```bash
uv run flask db upgrade 9b7c6d5e4f3a
uv run flask db stamp 5578e028b2f2
uv run flask db upgrade
```

启动 API 与 worker：

```bash
nohup uv run dotenv -f .env run --no-override -- python -m app > api.log 2>&1 &
nohup uv run dotenv -f .env run --no-override -- \
  celery -A app.celery worker -P prefork -c 2 --loglevel INFO \
  -Q workflow,conversation,plugin,dataset,dataset_summary,priority_dataset,priority_pipeline,pipeline,mail,ops_trace,app_deletion,workflow_storage,schedule_poller,schedule_executor,triggered_workflow_dispatcher,trigger_refresh_executor,retention,workflow_based_app_execution,knowledge_fs_lifecycle \
  > worker.log 2>&1 &
```

首次打开 `http://127.0.0.1:5001/install` 完成管理员与工作区初始化。Dify 控制台默认端口是 3000；
若只使用 DSL 导入与 Service API，可以只用 API + 本文脚本，不必起前端。

## 3. PowerContext

```bash
uv tool install powercontext        # 或 pip install powercontext
cp /path/to/dify/deploy/powercontext.env.example runtime/powercontext/.env
powercontext server run --env-file runtime/powercontext/.env
curl -s http://127.0.0.1:17429/health/ready
python3 /path/to/dify/scripts/verify_powercontext.py
```

`verify_powercontext.py` 会新建一个验证作用域、写入一条中文记忆并检索回来，输出 `"ok": true`。

## 4. 当铺网关

```bash
cd dify/gateway
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 至少确认：SEEKDB_PORT、POWERCONTEXT_URL、LLM_MODE、DIFY_BASE_URL/DIFY_API_KEY
./run.sh          # 也可以用 PYTHON=/path/to/python ./run.sh
```

启动后：

- `http://127.0.0.1:8099/`：记忆当铺体验页；
- `http://127.0.0.1:8099/api/health`：seekdb / PowerContext / Dify 代理 / 体验页状态；
- 模型未配置 Key 时 `LLM_MODE=mock`，离线也能完整玩；配好 `LLM_MODE=openai` + `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 即接真实模型。

## 5. 导入并发布 Dify 应用

```bash
cd dify
python3 scripts/publish_app.py \
  --dify-base http://127.0.0.1:5001 \
  --email admin@example.com \
  --password-file /path/to/admin-password.txt \
  --key-out /path/to/dify-app-key.txt
```

脚本会：登录控制台 → 删除同名旧应用 → 导入 `dsl/memory-pawnshop.yml` → 发布工作流 → 创建 Service API Key。
把输出的 Key 填进 `gateway/.env` 的 `DIFY_API_KEY`，重启网关即可在体验页使用。

DSL 里有一个环境变量 `GATEWAY_BASE`，默认 `http://127.0.0.1:8099`。
如果 Dify 跑在容器里而网关在宿主机，导入后要在 Dify 工作流的「环境变量」里把它改成
`http://host.docker.internal:8099` 或 compose 服务名。应用内没有使用 Code / Template 节点，
因此不需要额外起 `dify-sandbox`。

## 6. 验证

```bash
cd dify
python3 validation/run_e2e.py --cleanup     # 需要环境变量 DIFY_API_KEY（仅标准库）
gateway/.venv/bin/python scripts/verify_seekdb.py
```

`run_e2e.py` 会以新玩家跑「典当 → 赎回检索 → 确认赎回 → 重复确认 → 查账」，同时检查
PowerContext 的长期记忆召回，证据写入 `evidence/e2e-*.json|md`。

## 7. 已知边界

- `init_db.sql` 的 `WITH PARSER ik` 依赖 seekdb 的 IK 插件；不可用时 `init_db.py` 自动退回普通 FULLTEXT，
  再不可用则网关用 `LIKE` 检索，功能不中断。
- Dify 迁移临时表限制只影响空库初始化，已在上面给出安全跳过步骤；升级已有库时需单独评估。
- 体验页把 Dify Key 留在网关进程里，页面本身不接触 Key；网关默认只监听 `127.0.0.1`。
