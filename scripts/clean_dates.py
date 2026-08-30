# a helper script to fix date formats

import sqlite3
import re
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

def parse_and_normalize_date(date_str):
    if not date_str or date_str.lower() in ("unknown", "none", ""):
        return None
    
    date_str = date_str.strip()
    
    # Check if already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str

    # Common formats found in meeting minutes
    formats = [
        "%B %d, %Y",    # November 25, 2014
        "%b %d, %Y",    # Nov 25, 2014
        "%m/%d/%Y",     # 11/25/2014
        "%m-%d-%Y",     # 11-25-2014
        "%Y/%m/%d",     # 2014/11/25
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
            
    return None

def fix_dates():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT meeting_id, meeting_date FROM meetings")
    rows = cursor.fetchall()
    
    updated_count = 0
    for meeting_id, date_str in rows:
        normalized = parse_and_normalize_date(date_str)
        if normalized and normalized != date_str:
            cursor.execute(
                "UPDATE meetings SET meeting_date = ? WHERE meeting_id = ?",
                (normalized, meeting_id)
            )
            updated_count += 1
            
    conn.commit()
    conn.close()
    print(f"Normalized {updated_count} meeting dates.")

if __name__ == "__main__":
    fix_dates()