# Godot Docs Hybrid RAG 方案

## 目标

为清理后的 Godot Markdown 文档建立一套本地可复现的检索系统，让 AI 在回答问题前只读取少量高相关片段，而不是整批文档。第一版优先保证 API 符号查找准确，第二版再加入向量检索提升概念问题召回。

## 结论

采用 **SQLite Hybrid RAG**：

1. **符号索引**：解决 `Vector3`、`Node3D.get_position`、`StringName.is_valid_filename` 这类精确 API 查询。
2. **SQLite FTS5 全文检索**：解决错误信息、参数名、术语、普通关键词查询。
3. **向量检索**：作为第二阶段，解决“怎么做 2D 寻路”“什么时候用 signal”这类概念问题。
4. **轻量 rerank**：先用确定性规则合并排序，后续可接 cross-encoder 或 LLM rerank。

不要第一版只做向量库。Godot 文档里符号密度高，纯向量检索容易把精确 API 名称召回错，或者把概念相近但 API 不同的片段排到前面。

## 输入与输出

输入：

- RST 源目录：`../godot-docs`
- 清理后 Markdown：`../rpg_demo/godot-docs-md`
- 转换脚本：`rst2md_batch.py`

输出：

- SQLite 数据库：`./rag/godot_docs.sqlite`
- 可执行 CLI：`uv run python rag_cli.py build`
- 查询 CLI：`uv run python rag_cli.py search "Vector3 normalized"`

## 第一版范围

第一版只使用 Python 标准库和 SQLite FTS5，不依赖网络，不依赖外部 embedding API。

第一版必须完成：

- 读取 `../rpg_demo/godot-docs-md/**/*.md`
- 生成 chunk
- 抽取符号
- 写入 SQLite
- 支持符号检索
- 支持 FTS5 检索
- 支持 hybrid 合并排序
- 返回带路径、行号、标题、分数、片段文本的结果
- 有单元测试和一个小型端到端测试

第二版再做：

- embedding 表
- 向量召回
- rerank 模型或 LLM rerank
- 面向编辑器/代理的 HTTP API

## 推荐文件结构

```text
rag/
  __init__.py
  chunker.py          # Markdown -> Chunk
  symbols.py          # Chunk -> Symbol entries
  store.py            # SQLite schema/build/search primitives
  search.py           # Hybrid ranking orchestration
  models.py           # dataclasses only
rag_cli.py            # CLI entrypoint
tests/
  test_rag_chunker.py
  test_rag_symbols.py
  test_rag_search.py
```

## 数据模型

### `documents`

每个 Markdown 文件一行。

```sql
CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  doc_type TEXT NOT NULL,
  title TEXT NOT NULL
);
```

`doc_type` 取值：

- `class`：`classes/class_*.md`
- `tutorial`：`tutorials/**/*.md`
- `engine_detail`：`engine_details/**/*.md`
- `getting_started`：`getting_started/**/*.md`
- `other`：其他路径

### `chunks`

每个可检索片段一行。

```sql
CREATE TABLE chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  path TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  chunk_type TEXT NOT NULL,
  symbol TEXT NOT NULL DEFAULT '',
  heading TEXT NOT NULL DEFAULT '',
  breadcrumb TEXT NOT NULL DEFAULT '',
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  text TEXT NOT NULL
);
```

`chunk_type` 取值：

- `class_summary`
- `method`
- `property`
- `signal`
- `enum`
- `constant`
- `tutorial_section`
- `section`

### `chunks_fts`

```sql
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text,
  symbol,
  heading,
  breadcrumb,
  content='chunks',
  content_rowid='id',
  tokenize='unicode61'
);
```

### `symbols`

```sql
CREATE TABLE symbols (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  chunk_id INTEGER NOT NULL REFERENCES chunks(id),
  path TEXT NOT NULL
);

CREATE INDEX idx_symbols_normalized_name ON symbols(normalized_name);
CREATE INDEX idx_symbols_name ON symbols(name);
```

## Chunk 规则

### Class 文档

路径匹配：`classes/class_*.md`

类名从文件名和正文标题推断：

- `classes/class_aabb.md` -> `AABB`
- `classes/class_stringname.md` -> `StringName`
- `classes/class_@globalscope.md` -> `@GlobalScope`

分块规则：

1. 文件开头到第一个 API 成员标题之前，生成 `class_summary`。
2. 匹配属性签名行，生成 `property` chunk。
3. 匹配方法签名行，生成 `method` chunk。
4. 匹配 signal、enum、constant 区域，生成对应 chunk。
5. 每个成员 chunk 包含签名行和直到下一个成员签名前的说明。

成员签名识别以“保守准确”为准：

- 方法：行内同时包含 `**name**(` 和返回类型反引号。
- 属性：行内包含 `` `Type` **name** ``，但不包含 `(`。
- 运算符：行内包含 `**operator`。
- enum/constant：按 heading 或 `**NAME** =` 行识别。

### Tutorial 文档

路径匹配：`tutorials/**/*.md`

按 Markdown heading 切分：

- `#` 或 `##` 为主段。
- `###` 可并入上级，除非段落超过 1200 粗略 token。
- 每个 chunk 带 breadcrumb，例如 `tutorials > scripting > c_sharp > Variant`。

### Chunk 大小

目标：

- 最小：80 粗略 token
- 推荐：250-900 粗略 token
- 最大：1200 粗略 token

超大段落必须按段落边界切分，不能从代码块中间切。

## 符号抽取规则

从 class 文档抽取：

- 类名：`AABB`
- 属性：`AABB.position`
- 方法：`StringName.is_valid_filename`
- 运算符：`int.operator |`
- enum：`AStarGrid2D.Heuristic`
- constant：`RenderingDevice.BARRIER_MASK_RASTER`

从 tutorial 文档抽取：

- heading 中的 API 名称
- inline code 中出现的 `ClassName.method_name`、`ClassName`、`method_name()`

规范化规则：

- 全部转小写。
- 去掉 Markdown 标记。
- `class_`、`method_`、`property_` 这类内部前缀不得进入最终 symbol。
- `StringName.is_valid_filename()` 和 `StringName.is_valid_filename` 归一为同一个 normalized name。

## 查询流程

输入 query 后：

1. 归一化 query。
2. 判断是否像符号查询：
   - 包含 `.`
   - 包含 `()`
   - 包含 `_`
   - 包含首字母大写的 API 名
   - 与 symbols 表存在精确或前缀命中
3. 符号召回：
   - exact normalized match
   - suffix match，如 `is_valid_filename` 命中 `StringName.is_valid_filename`
   - prefix match，如 `Vector` 命中 `Vector2`、`Vector3`、`Vector4`
4. FTS5 召回：
   - 用 query 原文和规范化词查询 `chunks_fts`
   - 使用 `bm25(chunks_fts)` 排序
5. 合并去重：
   - 同一 `chunk_id` 只保留最高分来源
6. 加权排序：
   - exact symbol：+100
   - suffix symbol：+80
   - prefix symbol：+40
   - query 出现在 heading：+20
   - query 出现在 symbol：+30
   - class 文档 API 查询：+15
   - FTS5 bm25 转换为 0-40 分
7. 返回 top K，默认 8。

## 查询输出格式

每条结果必须包含：

```text
score: 132.5
path: classes/class_stringname.md:341-347
type: method
symbol: StringName.is_valid_filename
heading: Methods
breadcrumb: classes > StringName > is_valid_filename
text:
`bool` **is_valid_filename**() ...
Returns `true` if this string is a valid file name...
```

AI 读取时只把 top 5-10 条结果放进上下文。

## 验收标准

构建验收：

- `uv run python rag_cli.py build --docs ../rpg_demo/godot-docs-md --db rag/godot_docs.sqlite` 退出码为 0。
- 数据库包含 1500 个以上 documents。
- `chunks` 数量大于 documents 数量。
- `symbols` 数量大于 10000。

检索验收：

- 查询 `StringName.is_valid_filename`，第一条必须是 `classes/class_stringname.md` 的对应方法。
- 查询 `AABB position`，前 3 条必须包含 `classes/class_aabb.md`。
- 查询 `2D pathfinding grid`，前 5 条必须包含 `classes/class_astargrid2d.md` 或相关 tutorial。
- 查询 `C# Variant`，前 5 条必须包含 `tutorials/scripting/c_sharp/c_sharp_variant.md`。

质量验收：

- 返回片段中不得出现独立 `classref-*` 行。
- 返回片段中不得出现 `` `Type<class_Type>` `` 这种内部锚点格式，代码块里的原文除外。
- 每条结果必须有路径和行号。

## 风险与处理

### RST 到 MD 转换质量影响索引

处理：RAG 构建前先运行现有转换测试和全量转换抽样统计。

### 方法签名正则误判

处理：第一版正则保守，宁可少切一点，也不能把一个方法说明切断。验收用 `StringName.is_valid_filename`、`AABB.position`、`RenderingDevice` 这类样本覆盖。

### 纯向量召回不准

处理：第一版不把向量作为必要依赖；符号和 FTS5 必须独立可用。

### Chunk 太大导致 AI 读取效率低

处理：chunker 必须限制 1200 粗略 token，超限按段落切分。

## 第二阶段增强

第二阶段再增加：

- `embeddings` 表，存储 `chunk_id`、模型名、向量。
- 本地 embedding 或 OpenAI embedding。
- 查询时向量召回 top 30，与符号/FTS5 合并。
- 对合并后的 top 20 做 rerank，再返回 top 8。

第二阶段不得替代第一阶段的符号检索。符号检索是 Godot API 文档准确性的底座。
