# Godot Docs RAG 执行指令稿

这份指令稿给后续执行代理使用。目标是从当前仓库实现一个本地 SQLite Hybrid RAG，不依赖网络，先完成符号检索和 FTS5 检索。

## 执行前约束

1. 不要删除或重置用户已有改动。
2. 所有 shell 命令优先使用 `rtk` 前缀。
3. 生产代码必须先写失败测试，再写实现。
4. 不要覆盖正式 Markdown 输出目录，除非用户明确要求。
5. 第一版不要引入向量库、HTTP 服务、外部 API。
6. 第一版只使用 Python 标准库和 SQLite。

## 目标文件

需要创建：

```text
rag/
  __init__.py
  models.py
  chunker.py
  symbols.py
  store.py
  search.py
rag_cli.py
tests/test_rag_chunker.py
tests/test_rag_symbols.py
tests/test_rag_search.py
```

需要保留：

```text
rst2md_batch.py
tests/test_rst2md_batch.py
```

## 数据库位置

默认数据库：

```text
rag/godot_docs.sqlite
```

默认文档目录：

```text
../rpg_demo/godot-docs-md
```

## Task 1：建立数据模型

### Step 1：写失败测试

创建 `tests/test_rag_chunker.py`，先写以下测试：

```python
import unittest

from rag.models import Chunk


class ModelTests(unittest.TestCase):
    def test_chunk_has_required_fields(self):
        chunk = Chunk(
            path="classes/class_stringname.md",
            doc_type="class",
            chunk_type="method",
            symbol="StringName.is_valid_filename",
            heading="Methods",
            breadcrumb="classes > StringName > is_valid_filename",
            start_line=10,
            end_line=15,
            text="`bool` **is_valid_filename**()",
        )

        self.assertEqual(chunk.symbol, "StringName.is_valid_filename")
        self.assertEqual(chunk.start_line, 10)
        self.assertEqual(chunk.end_line, 15)


if __name__ == "__main__":
    unittest.main()
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_chunker.py
```

预期：失败，提示 `No module named 'rag'` 或 `Chunk` 不存在。

### Step 2：实现最小模型

创建 `rag/__init__.py`，内容为空。

创建 `rag/models.py`：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    path: str
    doc_type: str
    chunk_type: str
    symbol: str
    heading: str
    breadcrumb: str
    start_line: int
    end_line: int
    text: str


@dataclass(frozen=True)
class SearchResult:
    score: float
    path: str
    start_line: int
    end_line: int
    doc_type: str
    chunk_type: str
    symbol: str
    heading: str
    breadcrumb: str
    text: str
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_chunker.py
```

预期：通过。

提交：

```bash
rtk git add rag/__init__.py rag/models.py tests/test_rag_chunker.py
rtk git commit -m "feat: add rag data models"
```

如果用户没有要求提交，不要提交，只保留变更。

## Task 2：实现 Markdown chunker

### Step 1：补失败测试

在 `tests/test_rag_chunker.py` 添加：

```python
from rag.chunker import chunk_markdown


class ChunkerTests(unittest.TestCase):
    def test_chunks_class_summary_and_method(self):
        markdown = """# StringName

**Inherits:** `RefCounted` **<** `Object`

Interned string type.

## Methods

`bool` **is_valid_filename**() `const`

Returns `true` if this string is a valid file name.

`String` **validate_filename**()

Returns a safe file name.
"""

        chunks = chunk_markdown("classes/class_stringname.md", markdown)

        self.assertEqual(chunks[0].chunk_type, "class_summary")
        self.assertEqual(chunks[0].symbol, "StringName")
        self.assertEqual(chunks[1].chunk_type, "method")
        self.assertEqual(chunks[1].symbol, "StringName.is_valid_filename")
        self.assertIn("Returns `true`", chunks[1].text)
        self.assertEqual(chunks[1].start_line, 9)

    def test_chunks_tutorial_by_heading(self):
        markdown = """# C# Variant

Intro.

## Conversion

Use Variant carefully.

## Boxing

Avoid unnecessary boxing.
"""

        chunks = chunk_markdown("tutorials/scripting/c_sharp/c_sharp_variant.md", markdown)

        self.assertEqual([chunk.chunk_type for chunk in chunks], ["tutorial_section", "tutorial_section", "tutorial_section"])
        self.assertEqual(chunks[1].heading, "Conversion")
        self.assertIn("tutorials > scripting > c_sharp > c_sharp_variant > Conversion", chunks[1].breadcrumb)
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_chunker.py
```

预期：失败，提示 `rag.chunker` 不存在。

### Step 2：实现 chunker

创建 `rag/chunker.py`，实现：

- `chunk_markdown(path: str, markdown: str) -> list[Chunk]`
- `detect_doc_type(path: str) -> str`
- class 文件按 summary + 方法/属性切块
- tutorial 文件按 heading 切块
- 每个 chunk 带 start_line 和 end_line

必须满足：

```python
METHOD_RE = re.compile(r"`[^`]+` \*\*([A-Za-z_][A-Za-z0-9_]*)\*\*\(")
PROPERTY_RE = re.compile(r"`[^`]+` \*\*([A-Za-z_][A-Za-z0-9_]*)\*\*(?!\()")
```

class 名从路径推断：

```python
def class_name_from_path(path: str) -> str:
    stem = Path(path).stem
    raw = stem.removeprefix("class_")
    if raw == "@globalscope":
        return "@GlobalScope"
    return "".join(part.capitalize() for part in raw.split("_"))
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_chunker.py
```

预期：通过。

## Task 3：实现符号抽取

### Step 1：写失败测试

创建 `tests/test_rag_symbols.py`：

```python
import unittest

from rag.chunker import chunk_markdown
from rag.symbols import extract_symbols, normalize_symbol


class SymbolTests(unittest.TestCase):
    def test_normalizes_method_symbols(self):
        self.assertEqual(
            normalize_symbol("StringName.is_valid_filename()"),
            "stringname.is_valid_filename",
        )

    def test_extracts_class_and_method_symbols(self):
        markdown = """# StringName

## Methods

`bool` **is_valid_filename**() `const`

Returns `true`.
"""
        chunks = chunk_markdown("classes/class_stringname.md", markdown)
        symbols = extract_symbols(chunks)
        names = [symbol.name for symbol in symbols]

        self.assertIn("StringName", names)
        self.assertIn("StringName.is_valid_filename", names)


if __name__ == "__main__":
    unittest.main()
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_symbols.py
```

预期：失败，提示 `rag.symbols` 不存在。

### Step 2：实现 symbols

创建 `rag/symbols.py`：

- `Symbol` dataclass
- `normalize_symbol(name: str) -> str`
- `extract_symbols(chunks: list[Chunk]) -> list[Symbol]`

规则：

- class_summary chunk 生成 class symbol。
- method/property chunk 生成自己的 symbol。
- normalized name 小写，去掉尾部 `()`。

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_symbols.py
```

预期：通过。

## Task 4：实现 SQLite store

### Step 1：写失败测试

创建 `tests/test_rag_search.py`：

```python
import tempfile
import unittest
from pathlib import Path

from rag.chunker import chunk_markdown
from rag.store import build_database, search_database


class SearchTests(unittest.TestCase):
    def test_symbol_query_returns_exact_method_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs = Path(tmp) / "docs"
            docs.mkdir()
            classes = docs / "classes"
            classes.mkdir()
            (classes / "class_stringname.md").write_text(
                "# StringName\n\n"
                "## Methods\n\n"
                "`bool` **is_valid_filename**() `const`\n\n"
                "Returns `true` if this string is a valid file name.\n",
                encoding="utf-8",
            )
            db_path = Path(tmp) / "godot_docs.sqlite"

            build_database(docs, db_path)
            results = search_database(db_path, "StringName.is_valid_filename", limit=3)

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(results[0].symbol, "StringName.is_valid_filename")
            self.assertEqual(results[0].path, "classes/class_stringname.md")


if __name__ == "__main__":
    unittest.main()
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_search.py
```

预期：失败，提示 `rag.store` 不存在。

### Step 2：实现 store

创建 `rag/store.py`：

- `build_database(docs_dir: Path, db_path: Path) -> None`
- `search_database(db_path: Path, query: str, limit: int = 8) -> list[SearchResult]`

数据库必须包含：

- `documents`
- `chunks`
- `chunks_fts`
- `symbols`

构建流程：

1. 删除已有 db 文件。
2. 创建 schema。
3. 遍历 `docs_dir.rglob("*.md")`。
4. 调用 `chunk_markdown`。
5. 插入 documents/chunks。
6. 调用 `extract_symbols` 插入 symbols。
7. 同步写入 `chunks_fts`。

检索流程：

1. normalize query。
2. 查 `symbols.normalized_name = ?`，exact 命中加 100 分。
3. 查 `symbols.normalized_name LIKE ?`，suffix 命中加 80 分。
4. 查 FTS5，bm25 结果转为最高 40 分。
5. 按 chunk_id 合并。
6. 返回 score 降序 top K。

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_search.py
```

预期：通过。

## Task 5：实现 CLI

### Step 1：写 CLI 冒烟测试

在 `tests/test_rag_search.py` 增加一个 subprocess 测试：

```python
import subprocess
import sys


class CliTests(unittest.TestCase):
    def test_cli_help_runs(self):
        result = subprocess.run(
            [sys.executable, "rag_cli.py", "--help"],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("build", result.stdout)
        self.assertIn("search", result.stdout)
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_search.py
```

预期：失败，提示 `rag_cli.py` 不存在。

### Step 2：实现 CLI

创建 `rag_cli.py`：

支持：

```bash
rtk summary uv run python rag_cli.py build --docs ../rpg_demo/godot-docs-md --db rag/godot_docs.sqlite
rtk proxy uv run python rag_cli.py search "StringName.is_valid_filename" --db rag/godot_docs.sqlite --limit 5
```

`search` 输出格式必须包含：

```text
score:
path:
type:
symbol:
heading:
breadcrumb:
text:
```

运行：

```bash
rtk test uv run python -m unittest tests/test_rag_search.py
```

预期：通过。

## Task 6：全量构建验收

运行现有转换测试：

```bash
rtk test uv run python -m unittest tests/test_rst2md_batch.py
```

预期：

```text
OK
```

构建 RAG 数据库：

```bash
rtk summary uv run python rag_cli.py build --docs ../rpg_demo/godot-docs-md --db rag/godot_docs.sqlite
```

预期：

- 退出码 0。
- 输出 documents/chunks/symbols 数量。
- documents 大于 1500。
- chunks 大于 documents。
- symbols 大于 10000。

执行关键查询：

```bash
rtk proxy uv run python rag_cli.py search "StringName.is_valid_filename" --db rag/godot_docs.sqlite --limit 3
rtk proxy uv run python rag_cli.py search "AABB position" --db rag/godot_docs.sqlite --limit 3
rtk proxy uv run python rag_cli.py search "2D pathfinding grid" --db rag/godot_docs.sqlite --limit 5
rtk proxy uv run python rag_cli.py search "C# Variant" --db rag/godot_docs.sqlite --limit 5
```

验收：

- `StringName.is_valid_filename` 第一条是 `classes/class_stringname.md` 对应方法。
- `AABB position` 前 3 条包含 `classes/class_aabb.md`。
- `2D pathfinding grid` 前 5 条包含 `classes/class_astargrid2d.md` 或相关 tutorial。
- `C# Variant` 前 5 条包含 `tutorials/scripting/c_sharp/c_sharp_variant.md`。

## Task 7：最终质量检查

运行全部测试：

```bash
rtk test uv run python -m unittest discover tests
```

预期：

```text
OK
```

检查数据库文件：

```bash
rtk proxy ls -lh rag/godot_docs.sqlite
```

预期：文件存在，大小大于 1 MB。

检查 git 状态：

```bash
rtk git status --short
```

预期：只出现本次 RAG 实现相关文件。如果出现无关文件，不要修改或删除，向用户说明。

## 第二阶段指令

第一版验收通过后，才允许进入第二阶段。

第二阶段目标：

1. 增加 `embeddings` 表。
2. 为 chunk 生成 embedding。
3. 查询时执行 symbol + FTS5 + vector 三路召回。
4. 对 top 20 进行 rerank。
5. 保持第一版符号检索结果不退化。

第二阶段必须先写新的验收测试，证明 `StringName.is_valid_filename` 这类精确 API 查询仍然第一名。
