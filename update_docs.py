#!/usr/bin/env python3
"""更新 godot-docs RST 源并自动转换 RST → MD。

用法:
    uv run python update_docs.py -i ../path/to/godot-docs -o ../path/to/godot-docs-md
    uv run python update_docs.py -i ../path/to/godot-docs -o ../path/to/godot-docs-md -w 8
"""

import subprocess
import sys
from pathlib import Path

CWD = Path(__file__).parent


def main():
    import argparse
    parser = argparse.ArgumentParser(description="godot-docs RST → MD 更新工具")
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="godot-docs RST 源目录路径",
    )
    parser.add_argument(
        "-o", "--output",
        default="godot-docs-md",
        help="输出目录 (默认: godot-docs-md)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=8,
        help="并行进程数 (默认: 8)",
    )
    args = parser.parse_args()

    print(f"输入目录: {args.input}")
    print(f"输出目录: {args.output}")

    result = subprocess.run(
        [
            sys.executable, "rst2md_batch.py",
            "-i", args.input,
            "-o", args.output,
            "-w", str(args.workers),
        ],
        cwd=CWD,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
