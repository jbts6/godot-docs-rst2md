#!/usr/bin/env python3
"""
批量 RST → MD 转换。递归扫描目录下所有 .rst 文件。

用法:
    uv run python rst2md_batch.py
    uv run python rst2md_batch.py -i godot-docs -o godot-docs-md
    uv run python rst2md_batch.py --dry-run
    uv run python rst2md_batch.py -w 8
"""

import argparse
import os
import re
import subprocess
import shutil
import sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


WRAPPER_TAGS = (
    "div", "section", "span", "article", "aside",
    "nav", "header", "footer", "figure", "figcaption",
    "main", "details", "summary", "colgroup", "col",
    "thead", "tbody", "tfoot",
)


def convert_rst_to_md(rst_text: str) -> str:
    result = subprocess.run(
        ["pandoc", "-f", "rst", "-t", "gfm", "--wrap=none"],
        input=rst_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def clean_markdown(md: str) -> str:
    text = md

    # ── 移除包装性 HTML 标签 ──
    for tag in WRAPPER_TAGS:
        text = re.sub(rf"</?{tag}[^>]*>", "", text, flags=re.IGNORECASE)

    # ── 移除 HTML 注释 ──
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # ── RST 交叉引用 → 纯文本 ──
    text = re.sub(r":ref:`([^<`]+)\s*<[^>]+>`", r"\1", text)
    text = re.sub(r":doc:`([^`]+)`", r"\1", text)
    text = re.sub(r":math:`([^`]+)`", r"$\1$", text)
    text = re.sub(r":(\w+):`([^`]+)`", r"`\2`", text)

    # ── RST 指令行 ──
    text = re.sub(r"\.\.\s+(\w+)::", r"**\1:**", text)
    text = re.sub(r"^\.\.\s.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r":class:\s*\S+", "", text)

    # ── 空链接 ──
    text = re.sub(r"\[]$$[^)]*$$", "", text)

    # ── 去除噪音行 ──
    # RST transition
    text = re.sub(r"^-{4,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^={4,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*{4,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\^{4,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^~{4,}\s*$", "", text, flags=re.MULTILINE)

    # 表格分隔线 + 空数据行：
    # 匹配一行中"只有 |, -, :, 空格"的情况（至少含一个 | 或 -）
    # 保留含字母、数字、backtick 等实际内容的行
    text = re.sub(r"^\s*[\|\-][\|\-:\s]*$", "", text, flags=re.MULTILINE)

    # ── 压缩多余空行 ──
    text = re.sub(r"\n{3,}", "\n\n", text)

    # ── 去行尾空白 ──
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def process_one(rst_path: str, out_path: str) -> tuple[str, bool, str]:
    try:
        rst_text = Path(rst_path).read_text(encoding="utf-8")
        md_text = convert_rst_to_md(rst_text)
        md_text = clean_markdown(md_text)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        Path(out_path).write_text(md_text, encoding="utf-8")
        return (rst_path, True, f"{len(rst_text)}B → {len(md_text)}B")
    except Exception as e:
        return (rst_path, False, str(e))


def main():
    parser = argparse.ArgumentParser(description="批量 .rst → .md 转换")
    parser.add_argument(
        "-i", "--input",
        default="godot-docs",
        help="输入目录 (默认: godot-docs)",
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览文件映射，不实际转换",
    )

    args = parser.parse_args()

    if not shutil.which("pandoc"):
        print("错误: 未找到 pandoc。", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt install pandoc", file=sys.stderr)
        print("  macOS:         brew install pandoc", file=sys.stderr)
        sys.exit(1)

    input_root = Path(args.input).resolve()
    output_root = Path(args.output).resolve()

    if not input_root.is_dir():
        print(f"错误: 目录不存在 → {input_root}", file=sys.stderr)
        sys.exit(1)

    # 过滤文件
    rst_files = []
    for rst in input_root.rglob("*.rst"):
        rel = rst.relative_to(input_root)
        # 跳过 about 和 community 文件夹
        if "about" in rel.parts or "community" in rel.parts:
            continue
        # 跳过 404 和 index 文件
        if rel.stem in ["404", "index"]:
            continue
        rst_files.append(rst)
    
    rst_files = sorted(rst_files)
    total = len(rst_files)

    if total == 0:
        print(f"未找到需要处理的 .rst 文件: {input_root}")
        return

    print(f"输入目录: {input_root}")
    print(f"输出目录: {output_root}")
    print(f"找到 {total} 个 .rst 文件（已跳过 about/community 文件夹及 404/index 文件）\n")

    if args.dry_run:
        for rst in rst_files:
            rel = rst.relative_to(input_root)
            out = output_root / rel.with_suffix(".md")
            print(f"  {rst}  →  {out}")
        print(f"\n(dry-run，未实际转换)")
        return

    tasks = []
    for rst in rst_files:
        rel = rst.relative_to(input_root)
        out = output_root / rel.with_suffix(".md")
        tasks.append((str(rst), str(out)))

    ok_count = 0
    fail_count = 0

    if args.workers <= 1:
        for i, (rp, op) in enumerate(tasks, 1):
            _, success, msg = process_one(rp, op)
            status = "✓" if success else "✗"
            print(f"  [{i}/{total}] {status}  {rp}  {msg}")
            ok_count += success
            fail_count += (not success)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_one, rp, op): (rp, i)
                for i, (rp, op) in enumerate(tasks, 1)
            }
            for future in as_completed(futures):
                rp, idx = futures[future]
                _, success, msg = future.result()
                status = "✓" if success else "✗"
                print(f"  [{idx}/{total}] {status}  {rp}  {msg}")
                ok_count += success
                fail_count += (not success)

    print(f"\n完成: {ok_count} 成功, {fail_count} 失败, 共 {total}")


if __name__ == "__main__":
    main()
