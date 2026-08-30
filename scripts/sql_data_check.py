# a helper script to analyze sql lite data

import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- 1. SAMPLE OF 'UNKNOWN' DATES ---")
cursor.execute("""
    SELECT m.meeting_id, m.meeting_date, fts.issue_type, fts.topic_name 
    FROM meetings m
    JOIN meetings_fts fts ON m.meeting_id = fts.meeting_id
    WHERE m.meeting_date IS NULL OR m.meeting_date IN ('Unknown', 'None', '')
    LIMIT 10;
""")
for row in cursor.fetchall():
    print(dict(row))

print("\n--- 2. SAMPLE OF PIPE-SEPARATED CATEGORIES ---")
cursor.execute("""
    SELECT meeting_id, issue_type, topic_name 
    FROM meetings_fts 
    WHERE issue_type LIKE '%|%'
    LIMIT 10;
""")
for row in cursor.fetchall():
    print(dict(row))

conn.close()