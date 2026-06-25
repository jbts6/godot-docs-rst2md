import re
from pathlib import Path
from typing import List

from rag.models import Chunk

# Regex patterns for class members
METHOD_RE = re.compile(r"`[^`]+` \*\*([A-Za-z_][A-Za-z0-9_]*)\*\*\(")
PROPERTY_RE = re.compile(r"`[^`]+` \*\*([A-Za-z_][A-Za-z0-9_]*)\*\*(?!\()")
SIGNAL_RE = re.compile(r"^\*\*([A-Za-z_][A-Za-z0-9_]*)\*\*\(.*\)\s*$", re.MULTILINE)
ENUM_RE = re.compile(r"^enum\s+\*\*([A-Za-z_][A-Za-z0-9_]*)\*\*", re.MULTILINE)
CONSTANT_RE = re.compile(r"^\*\*([A-Z_][A-Z0-9_]*)\*\*\s*=", re.MULTILINE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def detect_doc_type(path: str) -> str:
    """Detect document type from path."""
    if path.startswith("classes/class_"):
        return "class"
    if path.startswith("tutorials/"):
        return "tutorial"
    if path.startswith("engine_details/"):
        return "engine_detail"
    if path.startswith("getting_started/"):
        return "getting_started"
    return "other"


def class_name_from_path(path: str) -> str:
    """Extract class name from file path."""
    stem = Path(path).stem
    raw = stem.removeprefix("class_")
    if raw == "@globalscope":
        return "@GlobalScope"
    return "".join(part.capitalize() for part in raw.split("_"))


def _find_headings(lines: List[str]) -> List[tuple]:
    """Find all headings with their positions."""
    headings = []
    for i, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            headings.append((i, level, title))
    return headings


def _class_name_from_heading(lines: List[str]) -> str:
    """Extract class name from the first H1 heading, fallback to path."""
    for line in lines:
        match = HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return ""


def _chunk_class_document(path: str, lines: List[str]) -> List[Chunk]:
    """Chunk a class document into summary and members."""
    chunks = []
    class_name = _class_name_from_heading(lines) or class_name_from_path(path)
    headings = _find_headings(lines)

    # Find first API member heading (Methods, Properties, Signals, etc.)
    first_member_idx = len(lines)
    for idx, level, title in headings:
        if title.lower() in ("methods", "properties", "signals", "enums", "constants", "operators"):
            first_member_idx = idx
            break

    # Class summary: from start to first member
    if first_member_idx > 0:
        summary_lines = lines[:first_member_idx]
        summary_text = "\n".join(summary_lines).strip()
        if summary_text:
            chunks.append(Chunk(
                path=path,
                doc_type="class",
                chunk_type="class_summary",
                symbol=class_name,
                heading=class_name,
                breadcrumb=f"classes > {class_name}",
                start_line=1,
                end_line=first_member_idx,
                text=summary_text,
            ))

    # Process members
    current_heading = ""
    current_heading_line = 0
    member_start = None
    member_symbol = None
    member_type = None

    for i in range(first_member_idx, len(lines)):
        line = lines[i]

        # Track current heading
        heading_match = HEADING_RE.match(line)
        if heading_match:
            current_heading = heading_match.group(2).strip()
            current_heading_line = i + 1
            continue

        # Check for method
        method_match = METHOD_RE.search(line)
        if method_match:
            # Save previous member if exists
            if member_start is not None and member_symbol:
                member_text = "\n".join(lines[member_start:i]).strip()
                if member_text:
                    chunks.append(Chunk(
                        path=path,
                        doc_type="class",
                        chunk_type=member_type,
                        symbol=member_symbol,
                        heading=current_heading,
                        breadcrumb=f"classes > {class_name} > {member_symbol.split('.')[-1]}",
                        start_line=member_start + 1,
                        end_line=i,
                        text=member_text,
                    ))

            method_name = method_match.group(1)
            member_symbol = f"{class_name}.{method_name}"
            member_type = "method"
            member_start = i
            continue

        # Check for property
        prop_match = PROPERTY_RE.search(line)
        if prop_match and "(" not in line:
            # Save previous member if exists
            if member_start is not None and member_symbol:
                member_text = "\n".join(lines[member_start:i]).strip()
                if member_text:
                    chunks.append(Chunk(
                        path=path,
                        doc_type="class",
                        chunk_type=member_type,
                        symbol=member_symbol,
                        heading=current_heading,
                        breadcrumb=f"classes > {class_name} > {member_symbol.split('.')[-1]}",
                        start_line=member_start + 1,
                        end_line=i,
                        text=member_text,
                    ))

            prop_name = prop_match.group(1)
            member_symbol = f"{class_name}.{prop_name}"
            member_type = "property"
            member_start = i
            continue

    # Save last member
    if member_start is not None and member_symbol:
        member_text = "\n".join(lines[member_start:]).strip()
        if member_text:
            chunks.append(Chunk(
                path=path,
                doc_type="class",
                chunk_type=member_type,
                symbol=member_symbol,
                heading=current_heading,
                breadcrumb=f"classes > {class_name} > {member_symbol.split('.')[-1]}",
                start_line=member_start + 1,
                end_line=len(lines),
                text=member_text,
            ))

    return chunks


def _chunk_tutorial_document(path: str, lines: List[str]) -> List[Chunk]:
    """Chunk a tutorial document by headings."""
    chunks = []
    headings = _find_headings(lines)

    # Build breadcrumb prefix from path
    parts = Path(path).parts
    breadcrumb_prefix = " > ".join(parts[:-1]) if len(parts) > 1 else parts[0]

    if not headings:
        # No headings, return whole document as one chunk
        text = "\n".join(lines).strip()
        if text:
            doc_name = Path(path).stem
            chunks.append(Chunk(
                path=path,
                doc_type="tutorial",
                chunk_type="tutorial_section",
                symbol="",
                heading="",
                breadcrumb=f"{breadcrumb_prefix} > {doc_name}",
                start_line=1,
                end_line=len(lines),
                text=text,
            ))
        return chunks

    # Process each heading section
    for i, (line_idx, level, title) in enumerate(headings):
        # Determine section end
        if i + 1 < len(headings):
            end_line = headings[i + 1][0]
        else:
            end_line = len(lines)

        # Get section content
        section_lines = lines[line_idx:end_line]
        section_text = "\n".join(section_lines).strip()

        if not section_text:
            continue

        # Build breadcrumb
        doc_name = Path(path).stem
        breadcrumb = f"{breadcrumb_prefix} > {doc_name} > {title}"

        chunks.append(Chunk(
            path=path,
            doc_type="tutorial",
            chunk_type="tutorial_section",
            symbol="",
            heading=title,
            breadcrumb=breadcrumb,
            start_line=line_idx + 1,
            end_line=end_line,
            text=section_text,
        ))

    return chunks


def chunk_markdown(path: str, markdown: str) -> List[Chunk]:
    """Chunk a markdown document into searchable pieces."""
    lines = markdown.split("\n")
    doc_type = detect_doc_type(path)

    if doc_type == "class":
        return _chunk_class_document(path, lines)
    elif doc_type == "tutorial":
        return _chunk_tutorial_document(path, lines)
    else:
        # Default: chunk by headings like tutorial
        return _chunk_tutorial_document(path, lines)
