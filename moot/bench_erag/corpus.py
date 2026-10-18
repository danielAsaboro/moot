"""The corpus in SQLite FTS5, ranked exactly the way Canon ranks it.

Same tokenizer (unicode61), same stopwords, same OR-of-terms query, same bm25 weights (title 2.0, content 1.0),
same 4,000-character window per document. Matching the baseline ranking is what makes the arms comparable.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from moot.bench_erag import DATA

TOKEN = re.compile(r"[A-Za-z0-9_]+")
STOPWORDS = frozenset((
    "a an and are as at be by for from has have how in is it its of on or that the this to was "
    "what when where which who why will with does do did should would could must our we you your "
    "their there these those been being into than then them they about after before between "
    "during over under up down out off again further once here all any both each few more most "
    "other some such no nor not only own same so too very can just now ").split())
MAX_DOC_CHARS = 4000


@dataclass(frozen=True, slots=True)
class Doc:
    doc_id: str
    source_type: str
    title: str
    content: str


def query_terms(text: str) -> list[str]:
    return list(dict.fromkeys(t for t in TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1))


class Corpus:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA / "corpus.sqlite"
        self.db = sqlite3.connect(self.path)

    def count(self) -> int:
        return self.db.execute("SELECT count(*) FROM documents").fetchone()[0]

    def search(self, question: str, k: int) -> list[str]:
        match = " OR ".join(f'"{t}"' for t in query_terms(question))
        if not match:
            return []
        rows = self.db.execute(
            "SELECT d.doc_id FROM (SELECT rowid AS rid, bm25(documents_fts, 2.0, 1.0) AS s FROM documents_fts "
            "WHERE documents_fts MATCH ? ORDER BY s LIMIT ?) r JOIN documents d ON d.rowid = r.rid ORDER BY r.s",
            (match, k)).fetchall()
        return [r[0] for r in rows]

    def doc(self, doc_id: str) -> Doc | None:
        row = self.db.execute("SELECT doc_id, source_type, title, content FROM documents WHERE doc_id = ?",
                              (doc_id,)).fetchone()
        return Doc(*row) if row else None


def window(content: str, question: str, max_chars: int = MAX_DOC_CHARS) -> str:
    """The densest max_chars of a long document, scored by question-term counts (Canon's relevant_window)."""
    if len(content) <= max_chars:
        return content
    terms = query_terms(question)
    if not terms:
        return content[:max_chars]
    low, step = content.lower(), max(1, max_chars // 4)
    best, best_score = 0, -1
    for start in range(0, max(1, len(content) - max_chars + step), step):
        score = sum(low[start:start + max_chars].count(t) for t in terms)
        if score > best_score:
            best, best_score = start, score
    return content[best:best + max_chars]


def build(parquet: Path | None = None, out: Path | None = None) -> dict:
    import pyarrow.parquet as pq
    parquet, out = parquet or DATA / "documents.parquet", out or DATA / "corpus.sqlite"
    if out.exists():
        n = sqlite3.connect(out).execute("SELECT count(*) FROM documents").fetchone()[0]
        return dict(db=str(out), indexed=n, note="already built; delete it to re-index")
    db = sqlite3.connect(out)
    db.executescript("""
        PRAGMA journal_mode=WAL; PRAGMA synchronous=OFF;
        CREATE TABLE documents (rowid INTEGER PRIMARY KEY, doc_id TEXT NOT NULL UNIQUE, source_type TEXT NOT NULL,
                                title TEXT NOT NULL, content TEXT NOT NULL);
        CREATE VIRTUAL TABLE documents_fts USING fts5(title, content, content='documents', content_rowid='rowid',
                                                       tokenize='unicode61');
    """)
    t0, inserted, skipped = time.time(), 0, 0
    for batch in pq.ParquetFile(parquet).iter_batches(batch_size=8192, columns=["doc_id", "source_type", "title", "content"]):
        b = batch.to_pydict()
        cur = db.cursor()
        for row in zip(b["doc_id"], b["source_type"], b["title"], b["content"], strict=True):
            r = cur.execute("INSERT OR IGNORE INTO documents(doc_id, source_type, title, content) VALUES (?,?,?,?)",
                            (row[0], row[1] or "", row[2] or "", row[3] or ""))
            if r.rowcount == 0:
                skipped += 1
                continue
            cur.execute("INSERT INTO documents_fts(rowid, title, content) VALUES (?,?,?)", (cur.lastrowid, row[2] or "", row[3] or ""))
            inserted += 1
        db.commit()
        print(f"indexed {inserted:,}", end="\r", file=sys.stderr)
    return dict(db=str(out), indexed=inserted, skipped_duplicates=skipped, seconds=round(time.time() - t0, 1))


if __name__ == "__main__":
    print(build())
