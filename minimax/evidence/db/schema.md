# seekdb 表结构与索引

生成命令：`/home/cuihaoyi/OceanBase/work/powercontext-ecosystem/minimax/sddctx/__main__.py ingest`

连接：`127.0.0.1:2893` · 库：`sdd_eco`

版本：`5.7.25-OceanBase seekdb-v1.4.0.0`

```sql
CREATE TABLE `sdd_documents` (
  `doc_id` varchar(96) NOT NULL,
  `kind` varchar(16) NOT NULL,
  `path` varchar(1024) NOT NULL,
  `sha256` char(64) NOT NULL,
  `item_count` int(11) NOT NULL DEFAULT '0',
  `imported_at` datetime(6) NOT NULL,
  PRIMARY KEY (`doc_id`),
  KEY `sdd_doc_kind` (`kind`) BLOCK_SIZE 16384 LOCAL,
  KEY `sdd_doc_path` (`path`(191)) BLOCK_SIZE 16384 LOCAL
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4 ROW_FORMAT = DYNAMIC COMPRESSION = 'zstd_1.3.8' BLOCK_SIZE = 16384 TABLET_SIZE = 134217728 PCTFREE = 0

-- sdd_documents
  -- 索引 PRIMARY 列 doc_id 类型 BTREE
  -- 索引 sdd_doc_kind 列 kind 类型 BTREE
  -- 索引 sdd_doc_path 列 path 类型 BTREE

CREATE TABLE `sdd_items` (
  `item_id` varchar(191) NOT NULL,
  `doc_id` varchar(96) NOT NULL,
  `kind` varchar(16) NOT NULL,
  `name` varchar(255) NOT NULL,
  `qualified_path` varchar(1024) NOT NULL,
  `start_line` int(11) NOT NULL,
  `end_line` int(11) NOT NULL,
  `text` mediumtext NOT NULL,
  `keywords` varchar(1024) NOT NULL DEFAULT '',
  `applies` varchar(1024) NOT NULL DEFAULT '',
  `entry_status` varchar(16) NOT NULL DEFAULT '',
  `sha256` char(64) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`item_id`),
  FULLTEXT KEY `sdd_item_ft` (`text`) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart") BLOCK_SIZE 16384,
  KEY `sdd_item_doc` (`doc_id`) BLOCK_SIZE 16384 LOCAL,
  KEY `sdd_item_kind` (`kind`, `name`(64)) BLOCK_SIZE 16384 LOCAL
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4 ROW_FORMAT = DYNAMIC COMPRESSION = 'zstd_1.3.8' BLOCK_SIZE = 16384 TABLET_SIZE = 134217728 PCTFREE = 0

-- sdd_items
  -- 索引 PRIMARY 列 item_id 类型 BTREE
  -- 索引 sdd_item_ft 列 text 类型 FULLTEXT
  -- 索引 sdd_item_doc 列 doc_id 类型 BTREE
  -- 索引 sdd_item_kind 列 kind 类型 BTREE
  -- 索引 sdd_item_kind 列 name 类型 BTREE

CREATE TABLE `sdd_query_log` (
  `log_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `task_id` varchar(64) NOT NULL DEFAULT '',
  `stage` varchar(64) NOT NULL,
  `sql_text` mediumtext NOT NULL,
  `terms` varchar(1024) NOT NULL DEFAULT '',
  `hit_count` int(11) NOT NULL DEFAULT '0',
  `elapsed_ms` int(11) NOT NULL DEFAULT '0',
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`log_id`),
  KEY `sdd_qlog_task` (`task_id`, `created_at`) BLOCK_SIZE 16384 LOCAL
) ORGANIZATION HEAP AUTO_INCREMENT = 1000303 DEFAULT CHARSET = utf8mb4 ROW_FORMAT = DYNAMIC COMPRESSION = 'zstd_1.3.8' BLOCK_SIZE = 16384 TABLET_SIZE = 134217728 PCTFREE = 0

-- sdd_query_log
  -- 索引 PRIMARY 列 log_id 类型 BTREE
  -- 索引 sdd_qlog_task 列 task_id 类型 BTREE
  -- 索引 sdd_qlog_task 列 created_at 类型 BTREE

CREATE TABLE `sdd_tasks` (
  `task_id` varchar(64) NOT NULL,
  `title` varchar(512) NOT NULL DEFAULT '',
  `statement` mediumtext NOT NULL,
  `keywords` varchar(1024) NOT NULL DEFAULT '',
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`task_id`)
) ORGANIZATION HEAP DEFAULT CHARSET = utf8mb4 ROW_FORMAT = DYNAMIC COMPRESSION = 'zstd_1.3.8' BLOCK_SIZE = 16384 TABLET_SIZE = 134217728 PCTFREE = 0

-- sdd_tasks
  -- 索引 PRIMARY 列 task_id 类型 BTREE
```

