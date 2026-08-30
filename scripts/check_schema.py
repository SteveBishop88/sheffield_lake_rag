# checks the sheffield_lake_rag.db

import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- TABLES IN DATABASE ---")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print([row[0] for row in cursor.fetchall()])

print("\n--- SCHEMA FOR 'meetings' TABLE ---")
cursor.execute("PRAGMA table_info(meetings);")
columns = cursor.fetchall()

if not columns:
    print("Table 'meetings' not found!")
else:
    for col in columns:
        # col format: (cid, name, type, notnull, dflt_value, pk)
        print(f"Column: {col[1]:<20} | Type: {col[2]}")

conn.close()

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "sheffield_lake_rag.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

print("--- SCHEMA FOR 'key_topics' TABLE ---")
cursor.execute("PRAGMA table_info(key_topics);")
for col in cursor.fetchall():
    print(f"Column: {col[1]:<20} | Type: {col[2]}")
conn.close()