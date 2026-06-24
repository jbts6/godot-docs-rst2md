import unittest

from rst2md_batch import clean_markdown


class CleanMarkdownTests(unittest.TestCase):
    def test_removes_classref_noise_lines(self):
        markdown = """
# AStarGrid2D

classref-introduction-group

Grid-based pathfinding.

classref-section-separator

More details.
"""

        self.assertEqual(
            clean_markdown(markdown),
            "# AStarGrid2D\n\nGrid-based pathfinding.\n\nMore details.",
        )

    def test_simplifies_godot_cross_references_but_keeps_display_text(self):
        markdown = (
            "**Inherits:** `RefCounted<class_RefCounted>` **\\<** "
            "`Object<class_Object>`\n\n"
            "Returns `Vector3<class_Vector3>` from `get_position<class_Node3D_method_get_position>`."
        )

        self.assertEqual(
            clean_markdown(markdown),
            "**Inherits:** `RefCounted` **<** `Object`\n\n"
            "Returns `Vector3` from `get_position`.",
        )

    def test_removes_anchor_icons_without_removing_method_text(self):
        markdown = (
            "`bool<class_bool>` **is_valid_filename**() "
            "`🔗<class_StringName_method_is_valid_filename>`\n\n"
            "Returns `true` for valid file names."
        )

        self.assertEqual(
            clean_markdown(markdown),
            "`bool` **is_valid_filename**()\n\nReturns `true` for valid file names.",
        )

    def test_does_not_clean_inside_fenced_code_blocks(self):
        markdown = """
```gdscript
print("classref-section-separator")
print("`Vector3<class_Vector3>`")
```

classref-section-separator

Outside `Vector3<class_Vector3>`.
"""

        self.assertEqual(
            clean_markdown(markdown),
            '```gdscript\nprint("classref-section-separator")\n'
            'print("`Vector3<class_Vector3>`")\n```\n\nOutside `Vector3`.',
        )

    def test_does_not_clean_inside_indented_code_blocks(self):
        markdown = """
Example:

    print("classref-section-separator")
    print("`Vector3<class_Vector3>`")

Outside `Vector3<class_Vector3>`.
"""

        self.assertEqual(
            clean_markdown(markdown),
            'Example:\n\n    print("classref-section-separator")\n'
            '    print("`Vector3<class_Vector3>`")\n\nOutside `Vector3`.',
        )


if __name__ == "__main__":
    unittest.main()
