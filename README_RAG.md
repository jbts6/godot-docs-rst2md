# Godot Docs RAG

本地 SQLite Hybrid RAG 系统，用于高效检索 Godot 文档。

## 安装

```bash
# 克隆仓库
git clone <repo-url> godot-docs-tools
cd godot-docs-tools

# 安装
uv pip install -e .
```

## 使用

### 构建数据库

```bash
godot-rag build --docs <markdown-docs-dir> --db rag/godot_docs.sqlite
```

### 搜索

```bash
# 文本输出
godot-rag search "StringName.is_valid_filename" --db rag/godot_docs.sqlite

# JSON 输出
godot-rag search "StringName.is_valid_filename" --db rag/godot_docs.sqlite --json

# 限制结果数量
godot-rag search "Timer" --db rag/godot_docs.sqlite --limit 5
```

### 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db` | SQLite 数据库路径 | 必填 |
| `--docs` | Markdown 文档目录 | build 必填 |
| `--limit` | 最大结果数 | 8 |
| `--json` | JSON 输出格式 | false |

## AI Agent 集成

### 系统提示词

```
回答 Godot 文档相关问题前，必须先调用本地 Godot Docs RAG。

调用规则：
- 如果用户提到类名、方法名、属性名，优先用精确符号查询。
- 如果用户问概念、教程、做法，用自然语言查询。
- 如果用户要求代码示例，同时查询相关 API 和相关教程。
- 如果第一次结果不足，最多再生成 2 个查询变体。
- 每次最多读取 8 个 chunk。
- 回答必须基于检索结果，不要凭记忆编造 API。
- 回答中标注来源路径和行号。
```

### 调用示例

```bash
# 精确 API 查询
godot-rag search "StringName.is_valid_filename" --db /path/to/godot_docs.sqlite --limit 5 --json

# 概念查询
godot-rag search "2D pathfinding" --db /path/to/godot_docs.sqlite --limit 5 --json
```

## 数据库位置

默认数据库路径：`rag/godot_docs.sqlite`

可以在游戏仓库中指定绝对路径：

```bash
godot-rag search "Timer" --db ~/godot-docs-tools/rag/godot_docs.sqlite
```

## 更新文档

当 Godot 文档更新时，重新构建数据库：

```bash
godot-rag build --docs <new-docs-dir> --db rag/godot_docs.sqlite
```
