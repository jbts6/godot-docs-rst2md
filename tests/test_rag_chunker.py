import unittest

from rag.models import Chunk
from rag.chunker import chunk_markdown


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


if __name__ == "__main__":
    unittest.main()
