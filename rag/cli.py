#!/usr/bin/env python3
"""CLI for Godot Docs RAG."""

import argparse
import json
import sys
from pathlib import Path

from rag.store import build_database, search_database


def cmd_build(args):
    """Build the RAG database."""
    docs_dir = Path(args.docs)
    db_path = Path(args.db)

    if not docs_dir.exists():
        print(f"Error: docs directory not found: {docs_dir}", file=sys.stderr)
        sys.exit(1)

    build_database(docs_dir, db_path)
    print(f"Database built at {db_path}")


def cmd_search(args):
    """Search the RAG database."""
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"Error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    results = search_database(db_path, args.query, limit=args.limit)

    if args.json:
        output = [
            {
                "score": r.score,
                "path": r.path,
                "start_line": r.start_line,
                "end_line": r.end_line,
                "doc_type": r.doc_type,
                "chunk_type": r.chunk_type,
                "symbol": r.symbol,
                "heading": r.heading,
                "breadcrumb": r.breadcrumb,
                "text": r.text,
            }
            for r in results
        ]
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results):
            if i > 0:
                print("---")
            print(f"score: {r.score}")
            print(f"path: {r.path}:{r.start_line}-{r.end_line}")
            print(f"type: {r.chunk_type}")
            print(f"symbol: {r.symbol}")
            print(f"heading: {r.heading}")
            print(f"breadcrumb: {r.breadcrumb}")
            print(f"text:\n{r.text}")


def main():
    parser = argparse.ArgumentParser(description="Godot Docs RAG CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build command
    build_parser = subparsers.add_parser("build", help="Build RAG database")
    build_parser.add_argument("--docs", required=True, help="Path to markdown docs directory")
    build_parser.add_argument("--db", required=True, help="Path to SQLite database")
    build_parser.set_defaults(func=cmd_build)

    # search command
    search_parser = subparsers.add_parser("search", help="Search RAG database")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--db", required=True, help="Path to SQLite database")
    search_parser.add_argument("--limit", type=int, default=8, help="Max results")
    search_parser.add_argument("--json", action="store_true", help="Output as JSON")
    search_parser.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
