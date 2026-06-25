import subprocess
import sys
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


class CliTests(unittest.TestCase):
    def test_cli_help_runs(self):
        result = subprocess.run(
            [sys.executable, "-m", "rag.cli", "--help"],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("build", result.stdout)
        self.assertIn("search", result.stdout)


if __name__ == "__main__":
    unittest.main()
