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
