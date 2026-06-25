import re
import sqlite3
from pathlib import Path
from typing import List

from rag.chunker import chunk_markdown
from rag.models import SearchResult
from rag.symbols import extract_symbols, normalize_symbol

# Patterns for cleaning text
CLASSREF_LINE_RE = re.compile(r"^\s*classref-\S+\s*$", re.MULTILINE)
ANCHOR_RE = re.compile(r"`([^`<]+)<class_[^>]+>`")


def clean_chunk_text(text: str) -> str:
    """Clean chunk text by removing classref noise and internal anchors."""
    # Remove standalone classref-* lines
    text = CLASSREF_LINE_RE.sub("", text)
    # Remove <class_*> anchors, keep display text
    text = ANCHOR_RE.sub(r"`\1`", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  doc_type TEXT NOT NULL,
  title TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
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

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text,
  symbol,
  heading,
  breadcrumb,
  content='chunks',
  content_rowid='id',
  tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS symbols (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  kind TEXT NOT NULL,
  chunk_id INTEGER NOT NULL REFERENCES chunks(id),
  path TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_normalized_name ON symbols(normalized_name);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
"""

FTS_SYNC = """
INSERT INTO chunks_fts(rowid, text, symbol, heading, breadcrumb)
SELECT id, text, symbol, heading, breadcrumb FROM chunks;
"""


def build_database(docs_dir: Path, db_path: Path) -> None:
    """Build the RAG database from markdown docs."""
    # Remove existing db
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

    md_files = sorted(docs_dir.rglob("*.md"))
    for md_file in md_files:
        rel_path = str(md_file.relative_to(docs_dir))
        markdown = md_file.read_text(encoding="utf-8")
        chunks = chunk_markdown(rel_path, markdown)

        if not chunks:
            continue

        # Detect doc_type from first chunk
        doc_type = chunks[0].doc_type if chunks else "other"

        # Extract title from first chunk or path
        title = chunks[0].heading if chunks else Path(rel_path).stem

        # Insert document
        cur = conn.execute(
            "INSERT OR IGNORE INTO documents (path, doc_type, title) VALUES (?, ?, ?)",
            (rel_path, doc_type, title),
        )
        doc_id = cur.lastrowid
        if doc_id == 0:
            row = conn.execute("SELECT id FROM documents WHERE path = ?", (rel_path,)).fetchone()
            doc_id = row[0]

        # Insert chunks
        for chunk in chunks:
            cleaned_text = clean_chunk_text(chunk.text)
            conn.execute(
                "INSERT INTO chunks (document_id, path, doc_type, chunk_type, symbol, heading, breadcrumb, start_line, end_line, text) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (doc_id, chunk.path, chunk.doc_type, chunk.chunk_type, chunk.symbol, chunk.heading, chunk.breadcrumb, chunk.start_line, chunk.end_line, cleaned_text),
            )

        # Extract and insert symbols
        chunk_ids = [row[0] for row in conn.execute(
            "SELECT id FROM chunks WHERE document_id = ? ORDER BY id",
            (doc_id,),
        ).fetchall()]

        symbols = extract_symbols(chunks)
        for sym, chunk_id in zip(symbols, chunk_ids[:len(symbols)]):
            conn.execute(
                "INSERT INTO symbols (name, normalized_name, kind, chunk_id, path) VALUES (?, ?, ?, ?, ?)",
                (sym.name, sym.normalized_name, sym.kind, chunk_id, sym.path),
            )

    # Sync FTS index
    conn.executescript(FTS_SYNC)
    conn.commit()
    conn.close()


def search_database(db_path: Path, query: str, limit: int = 8) -> List[SearchResult]:
    """Search the RAG database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    normalized = normalize_symbol(query)
    results = {}

    # 1. Exact symbol match (+100)
    rows = conn.execute(
        "SELECT s.name, c.* FROM symbols s JOIN chunks c ON s.chunk_id = c.id WHERE s.normalized_name = ?",
        (normalized,),
    ).fetchall()
    for row in rows:
        cid = row["id"]
        if cid not in results or results[cid]["score"] < 100:
            results[cid] = {
                "score": 100.0,
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "doc_type": row["doc_type"],
                "chunk_type": row["chunk_type"],
                "symbol": row["symbol"],
                "heading": row["heading"],
                "breadcrumb": row["breadcrumb"],
                "text": row["text"],
            }

    # 2. Suffix symbol match (+80)
    rows = conn.execute(
        "SELECT s.name, c.* FROM symbols s JOIN chunks c ON s.chunk_id = c.id WHERE s.normalized_name LIKE ?",
        (f"%.{normalized}",),
    ).fetchall()
    for row in rows:
        cid = row["id"]
        if cid not in results or results[cid]["score"] < 80:
            results[cid] = {
                "score": 80.0,
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "doc_type": row["doc_type"],
                "chunk_type": row["chunk_type"],
                "symbol": row["symbol"],
                "heading": row["heading"],
                "breadcrumb": row["breadcrumb"],
                "text": row["text"],
            }

    # 3. Prefix symbol match (+40)
    rows = conn.execute(
        "SELECT s.name, c.* FROM symbols s JOIN chunks c ON s.chunk_id = c.id WHERE s.normalized_name LIKE ?",
        (f"{normalized}%",),
    ).fetchall()
    for row in rows:
        cid = row["id"]
        if cid not in results or results[cid]["score"] < 40:
            results[cid] = {
                "score": 40.0,
                "path": row["path"],
                "start_line": row["start_line"],
                "end_line": row["end_line"],
                "doc_type": row["doc_type"],
                "chunk_type": row["chunk_type"],
                "symbol": row["symbol"],
                "heading": row["heading"],
                "breadcrumb": row["breadcrumb"],
                "text": row["text"],
            }

    # 4. FTS5 search (bm25 → 0-40 score)
    try:
        fts_rows = conn.execute(
            "SELECT c.*, bm25(chunks_fts) as rank FROM chunks_fts fts JOIN chunks c ON fts.rowid = c.id WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit * 3),
        ).fetchall()
        for row in fts_rows:
            cid = row["id"]
            bm25 = abs(row["rank"])
            fts_score = min(40.0, max(0.0, 40.0 / (1.0 + bm25 * 0.1)))
            if cid not in results or results[cid]["score"] < fts_score:
                results[cid] = {
                    "score": fts_score,
                    "path": row["path"],
                    "start_line": row["start_line"],
                    "end_line": row["end_line"],
                    "doc_type": row["doc_type"],
                    "chunk_type": row["chunk_type"],
                    "symbol": row["symbol"],
                    "heading": row["heading"],
                    "breadcrumb": row["breadcrumb"],
                    "text": row["text"],
                }
    except sqlite3.OperationalError:
        # FTS match syntax error, skip
        pass

    conn.close()

    # Sort by score descending
    sorted_results = sorted(results.values(), key=lambda r: r["score"], reverse=True)
    return [
        SearchResult(
            score=r["score"],
            path=r["path"],
            start_line=r["start_line"],
            end_line=r["end_line"],
            doc_type=r["doc_type"],
            chunk_type=r["chunk_type"],
            symbol=r["symbol"],
            heading=r["heading"],
            breadcrumb=r["breadcrumb"],
            text=r["text"],
        )
        for r in sorted_results[:limit]
    ]
