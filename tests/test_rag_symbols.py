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
