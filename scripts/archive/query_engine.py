# Queries the SQLite database using FTS5 for structured meeting searches

import sqlite3
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

def search_sqlite_fts(
    query_text: str, 
    limit: int = 5, 
    start_year: int = None, 
    end_year: int = None, 
    category_filter: str = None
):
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    fts_query = " AND ".join(query_text.strip().split())

    # Reference meetings_fts directly in bm25() and MATCH
    sql = """
        SELECT 
            m.meeting_id,
            m.source_filename,
            m.meeting_date,
            m.category,
            fts.topic_name,
            fts.description,
            fts.issue_type,
            bm25(meetings_fts) AS score
        FROM meetings_fts fts
        JOIN meetings m ON fts.meeting_id = m.meeting_id
        WHERE meetings_fts MATCH ?
    """
    params = [fts_query]

    if start_year:
        sql += " AND CAST(substr(m.meeting_date, 1, 4) AS INT) >= ?"
        params.append(start_year)
    if end_year:
        sql += " AND CAST(substr(m.meeting_date, 1, 4) AS INT) <= ?"
        params.append(end_year)
    if category_filter:
        sql += " AND m.category LIKE ?"
        params.append(f"%{category_filter}%")

    sql += " ORDER BY score ASC LIMIT ?"
    params.append(limit)

    start_time = time.perf_counter()
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print(f"\n--- Query: '{query_text}' | Results: {len(rows)} | Time: {elapsed_ms:.2f} ms ---")
    for idx, row in enumerate(rows, 1):
        print(f"\n[{idx}] Meeting ID: {row['meeting_id']} | Date: {row['meeting_date']} | Category: {row['category']}")
        print(f"    Topic: {row['topic_name']} ({row['issue_type']})")
        print(f"    File: {row['source_filename']}")
        print(f"    Description: {row['description'][:200]}...")

    conn.close()
    return rows

if __name__ == "__main__":
    search_sqlite_fts("stormwater", limit=5)