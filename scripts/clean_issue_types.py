# a helper file to clean up multiple issue types in a single field eg:
# 'issue_type': 'Infrastructure | Budget'

import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 1. Fetch all rows with pipe-separated issue types
cursor.execute("SELECT rowid, issue_type FROM meetings_fts WHERE issue_type LIKE '%|%'")
rows = cursor.fetchall()

print(f"Found {len(rows)} pipe-separated categories to clean up.")

# 2. Update each row to take only the primary (first) category
updated_count = 0
for rowid, issue_type in rows:
    primary_category = issue_type.split('|')[0].strip()
    cursor.execute(
        "UPDATE meetings_fts SET issue_type = ? WHERE rowid = ?",
        (primary_category, rowid)
    )
    updated_count += 1

conn.commit()
conn.close()

print(f"Successfully normalized {updated_count} categories to their primary classification!")