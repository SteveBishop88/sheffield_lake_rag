import os
import json
import sqlite3
from pathlib import Path

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
JSON_DIR = PROJECT_ROOT / "data" / "extracted_json"
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

def init_db(conn):
    """Create normalized relational tables and an FTS5 virtual table for fast search."""
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 1. Main Meetings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS meetings (
        meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_filename TEXT UNIQUE,
        meeting_date TEXT,
        category TEXT,
        page_count INTEGER
    );
    """)

    # 2. Key Topics Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS key_topics (
        topic_id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER,
        topic_name TEXT,
        description TEXT,
        issue_type TEXT,
        FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id) ON DELETE CASCADE
    );
    """)

    # 3. Entities Mentioned Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS topic_entities (
        entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_id INTEGER,
        entity_name TEXT,
        FOREIGN KEY (topic_id) REFERENCES key_topics (topic_id) ON DELETE CASCADE
    );
    """)

    # 4. Action Items & Votes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS action_items (
        action_id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER,
        action_text TEXT,
        FOREIGN KEY (meeting_id) REFERENCES meetings (meeting_id) ON DELETE CASCADE
    );
    """)

    # 5. Full-Text Search (FTS5) Virtual Table for RAG Keyword Search
    cursor.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
        topic_name,
        description,
        issue_type,
        category,
        meeting_date,
        content='key_topics',
        content_rowid='topic_id'
    );
    """)

    conn.commit()

def load_json_to_sqlite():
    if not JSON_DIR.exists():
        print(f"[!] JSON directory {JSON_DIR} does not exist yet.")
        return

    json_files = list(JSON_DIR.glob("*.json"))
    if not json_files:
        print(f"[!] No JSON files found in {JSON_DIR}.")
        return

    # Ensure the target db/ directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"[+] Found {len(json_files)} extracted JSON files to process...")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    cursor = conn.cursor()

    loaded_count = 0
    skipped_count = 0

    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            filename = data.get("source_filename", json_path.stem + ".pdf")

            # Check if already inserted
            cursor.execute("SELECT meeting_id FROM meetings WHERE source_filename = ?", (filename,))
            existing = cursor.fetchone()
            if existing:
                skipped_count += 1
                continue

            # Insert Meeting record
            cursor.execute("""
                INSERT INTO meetings (source_filename, meeting_date, category, page_count)
                VALUES (?, ?, ?, ?)
            """, (
                filename,
                data.get("meeting_date", "Unknown"),
                data.get("category", "General"),
                data.get("page_count", 0)
            ))
            meeting_id = cursor.lastrowid

            # Insert Topics and Entities
            for topic in data.get("key_topics", []):
                if isinstance(topic, dict):
                    t_name = topic.get("topic_name", "General Topic")
                    t_desc = topic.get("description", "")
                    i_type = topic.get("issue_type", "General")

                    cursor.execute("""
                        INSERT INTO key_topics (meeting_id, topic_name, description, issue_type)
                        VALUES (?, ?, ?, ?)
                    """, (meeting_id, t_name, t_desc, i_type))
                    topic_id = cursor.lastrowid

                    # Populate FTS Index
                    cursor.execute("""
                        INSERT INTO topics_fts (rowid, topic_name, description, issue_type, category, meeting_date)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (topic_id, t_name, t_desc, i_type, data.get("category", "General"), data.get("meeting_date", "Unknown")))

                    # Insert Entities
                    for entity in topic.get("entities_involved", []):
                        ent_str = entity.get("name", "") if isinstance(entity, dict) else str(entity)
                        if ent_str and ent_str.strip():
                            cursor.execute("""
                                INSERT INTO topic_entities (topic_id, entity_name)
                                VALUES (?, ?)
                            """, (topic_id, ent_str.strip()))

            # Insert Action Items / Votes
            for action in data.get("action_items_or_votes", []):
                act_str = action.get("text", "") if isinstance(action, dict) else str(action)
                if act_str and act_str.strip():
                    cursor.execute("""
                        INSERT INTO action_items (meeting_id, action_text)
                        VALUES (?, ?)
                    """, (meeting_id, act_str.strip()))

            loaded_count += 1

        except Exception as e:
            print(f"[!] Error loading {json_path.name}: {e}")

    conn.commit()
    conn.close()

    print("\nDatabase load complete!")
    print(f"Newly Loaded: {loaded_count} | Skipped (Already Present): {skipped_count}")
    print(f"Database Path: {DB_PATH}")

if __name__ == "__main__":
    load_json_to_sqlite()