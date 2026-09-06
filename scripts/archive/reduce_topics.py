#This script aggregates every .json file in extracted_json/, 
#tallies issue categories, counts topic frequencies, 
#maps recurring entities, and feeds those structured summaries 
#into llama3 for macro-level analysis.

# for a gui interface, this file would drive the macro 30,000 foot view
# of general topics over a 20 year period.

#queries a sqllite db instead of raw .json


import sqlite3
import json
import requests
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

def fetch_corpus_stats():
    """Run fast SQL aggregation across the entire database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Total meetings
    cursor.execute("SELECT COUNT(*) FROM meetings")
    total_meetings = cursor.fetchone()[0]

    # Category Breakdown
    cursor.execute("SELECT category, COUNT(*) FROM meetings GROUP BY category ORDER BY COUNT(*) DESC")
    categories = dict(cursor.fetchall())

    # Issue Types Breakdown
    cursor.execute("SELECT issue_type, COUNT(*) FROM key_topics GROUP BY issue_type ORDER BY COUNT(*) DESC")
    issue_types = dict(cursor.fetchall())

    # Top Entities
    cursor.execute("SELECT entity_name, COUNT(*) FROM topic_entities GROUP BY entity_name ORDER BY COUNT(*) DESC LIMIT 15")
    top_entities = dict(cursor.fetchall())

    # Sample top topics across categories
    cursor.execute("""
        SELECT m.meeting_date, m.category, t.topic_name, t.description 
        FROM key_topics t
        JOIN meetings m ON t.meeting_id = m.meeting_id
        ORDER BY m.meeting_date DESC
        LIMIT 40
    """)
    samples = cursor.fetchall()
    conn.close()

    return {
        "total_meetings": total_meetings,
        "categories": categories,
        "issue_types": issue_types,
        "top_entities": top_entities,
        "sample_topics": [f"[{row[0]} | {row[1]}] {row[2]}: {row[3]}" for row in samples]
    }

def synthesize_macro_analysis(stats):
    prompt = f"""You are a senior municipal policy analyst reviewing City of Sheffield Lake records.
Below is an aggregated statistical summary extracted from {stats['total_meetings']} municipal meetings:

STATISTICAL BREAKDOWN:
- Active Categories: {json.dumps(stats['categories'])}
- Issue Types: {json.dumps(stats['issue_types'])}
- Most Frequently Mentioned Entities/Locations: {json.dumps(stats['top_entities'])}

SAMPLE TOPICS ACROSS RECENT YEARS:
{chr(10).join(stats['sample_topics'])}

TASK:
1. Identify the TOP 3 overarching municipal priorities facing Sheffield Lake.
2. For each priority, explain recurring challenges and key streets or entities involved.
3. Summarize primary actions and resolutions passed by city council.
"""

    payload = {"model": MODEL_NAME, "prompt": prompt, "stream": True}

    print("\n================ MACRO-ANALYSIS REDUCE PASS ================")
    print(f"Synthesizing {stats['total_meetings']} meeting records from SQLite...\n")

    try:
        response = requests.post(OLLAMA_URL, json=payload, stream=True)
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                data = json.loads(line.decode("utf-8"))
                print(data.get("response", ""), end="", flush=True)
        print("\n===========================================================\n")
    except Exception as e:
        print(f"[!] Error calling Ollama: {e}")

if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"[!] Database not found at {DB_PATH}. Run load_to_sqlite.py first.")
    else:
        stats = fetch_corpus_stats()
        synthesize_macro_analysis(stats)