# Creates and populates the SQLite FTS5 virtual table for sub-millisecond 
# full-text search and keyword stemming across municipal meeting records.


# Creates and populates the SQLite FTS5 virtual table for sub-millisecond 
# full-text search and keyword stemming across municipal meeting records.

# Creates and populates the SQLite FTS5 virtual table for sub-millisecond 
# full-text search and keyword stemming across municipal meeting records.

import sqlite3
import time
from pathlib import Path

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

def build_fts_index():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print(" BUILDING FTS5 FULL-TEXT SEARCH INDEX")
    print("=" * 60)

    # Step 1: Drop existing FTS table if it exists (for a clean rebuild)
    cursor.execute("DROP TABLE IF EXISTS meetings_fts")
    print("\n[1/4] Dropped old meetings_fts virtual table (if present).")

    # Step 2: Create the FTS5 Virtual Table using actual key_topics columns
    cursor.execute("""
        CREATE VIRTUAL TABLE meetings_fts USING fts5(
            meeting_id UNINDEXED,
            source_filename,
            category,
            topic_name,
            description,
            issue_type,
            tokenize='porter ascii'
        )
    """)
    print("[2/4] Created new meetings_fts virtual table with Porter Stemmer.")

    # Step 3: Populate FTS5 table by joining meetings with key_topics
    start_time = time.perf_counter()
    cursor.execute("""
        INSERT INTO meetings_fts(meeting_id, source_filename, category, topic_name, description, issue_type)
        SELECT 
            m.meeting_id,
            m.source_filename,
            m.category,
            t.topic_name,
            t.description,
            t.issue_type
        FROM meetings m
        JOIN key_topics t ON m.meeting_id = t.meeting_id
    """)
    conn.commit()
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    
    rows_indexed = cursor.rowcount
    print(f"[3/4] Indexed {rows_indexed:,} topic records in {elapsed_ms:.2f} ms.")

    # Step 4: Verify the index
    cursor.execute("SELECT COUNT(*) FROM meetings_fts")
    count = cursor.fetchone()[0]
    print(f"[4/4] Verification: {count:,} records active in meetings_fts.")

    conn.close()
    print("\nFTS5 index build complete! Ready for query execution.")
    print("=" * 60)

if __name__ == "__main__":
    build_fts_index()