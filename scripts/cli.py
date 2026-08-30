# Interactive CLI for searching Sheffield Lake municipal meeting records using FTS5 + Ollama RAG
import sys
import sqlite3
import time
import re
from pathlib import Path
import urllib.request
import json

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"

class SQLiteRAGChain:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path

    # Common stop words to strip so natural language queries don't break SQLite FTS
    STOP_WORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
        "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
        "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
        "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
        "have", "haven't", "having", "he", "her", "here", "him", "his", "how", "i",
        "if", "in", "into", "is", "isn't", "it", "it's", "its", "me", "more", "most",
        "my", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
        "our", "ours", "out", "over", "own", "same", "she", "should", "so", "some",
        "such", "than", "that", "the", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "to", "too", "under", "until", "up",
        "very", "was", "wasn't", "we", "were", "what", "what's", "when", "where",
        "which", "while", "who", "whom", "why", "will", "with", "won't", "would",
        "you", "your", "yours"
    }

    def sanitize_fts_query(self, raw_query: str) -> str:
        # Extract alphanumeric words
        words = re.findall(r'\b\w+\b', raw_query)
        if not words:
            return ""

        # Remove common stop words to leave core search terms
        meaningful_words = [w for w in words if w.lower() not in self.STOP_WORDS]

        # Fallback to original words if the entire query consisted of stop words
        if not meaningful_words:
            meaningful_words = words

        # Join remaining terms with FTS AND logic
        return " AND ".join(f'"{word}"' for word in meaningful_words)

    # --------------------------------------------------------------------------
    # Database Inspection & Data Verification Methods
    # --------------------------------------------------------------------------

    # What it answers: "What general domain consumes most of the city's time?"
    def get_all_distinct_issues(self):
        """Returns clean aggregated distinct issue types with valid date ranges."""
        if not self.db_path.exists():
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql = """
            SELECT 
                fts.issue_type,
                COUNT(*) as mention_count,
                COALESCE(
                    MIN(CASE WHEN m.meeting_date NOT IN ('Unknown', 'None', '') THEN m.meeting_date END), 
                    'Unknown'
                ) as earliest_date,
                COALESCE(
                    MAX(CASE WHEN m.meeting_date NOT IN ('Unknown', 'None', '') THEN m.meeting_date END), 
                    'Unknown'
                ) as latest_date,
                fts.topic_name AS topic_name
            FROM meetings_fts fts
            JOIN meetings m ON fts.meeting_id = m.meeting_id
            WHERE fts.issue_type IS NOT NULL AND fts.issue_type != ''
            GROUP BY fts.issue_type
            ORDER BY mention_count DESC, fts.issue_type ASC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_database_schema(self):
        """Retrieves all table names, column definitions, and row counts from sqlite_master."""
        if not self.db_path.exists():
            return {}

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]

        schema_info = {}
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [(row[1], row[2]) for row in cursor.fetchall()]
            
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                row_count = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                row_count = 0

            schema_info[table] = {
                "columns": columns,
                "row_count": row_count
            }

        conn.close()
        return schema_info

    def retrieve_context(
        self, 
        query: str, 
        limit: int = 5, 
        start_year: int = None, 
        end_year: int = None, 
        category_filter: str = None
    ):
        if not self.db_path.exists():
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        fts_query = self.sanitize_fts_query(query)
        if not fts_query:
            conn.close()
            return []

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

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    # What it answers: "What are the most heavily discussed specific 
    # recurring items across all meetings?"
    def retrieve_top_issues(
        self, 
        limit: int = 10, 
        start_year: int = None, 
        end_year: int = None, 
        category_filter: str = None
    ):
        if not self.db_path.exists():
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # SQL aggregates across ALL records matching active filters
        sql = """
            SELECT 
                fts.issue_type,
                fts.topic_name,
                COUNT(*) as mention_count,
                MIN(m.meeting_date) as earliest_date,
                MAX(m.meeting_date) as latest_date
            FROM meetings_fts fts
            JOIN meetings m ON fts.meeting_id = m.meeting_id
            WHERE fts.issue_type IS NOT NULL AND fts.issue_type != ''
        """
        params = []

        if start_year:
            sql += " AND CAST(substr(m.meeting_date, 1, 4) AS INT) >= ?"
            params.append(start_year)
        if end_year:
            sql += " AND CAST(substr(m.meeting_date, 1, 4) AS INT) <= ?"
            params.append(end_year)
        if category_filter:
            sql += " AND m.category LIKE ?"
            params.append(f"%{category_filter}%")

        sql += """
            GROUP BY fts.issue_type, fts.topic_name
            ORDER BY mention_count DESC
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def build_prompt(self, query: str, rows) -> str:
        context_str = ""
        for r in rows:
            context_str += f"\n--- MEETING RECORD: {r['meeting_id']} ({r['meeting_date']}) ---\n"
            context_str += f"Category: {r['category']}\n"
            context_str += f"File: {r['source_filename']}\n"
            context_str += f"Topic: {r['topic_name']} ({r['issue_type']})\n"
            context_str += f"Description: {r['description']}\n"

        return f"""You are an expert municipal analyst for the City of Sheffield Lake.
Answer the question below accurately using ONLY the provided meeting records context.

CONTEXT:
{context_str}

QUESTION:
{query}

ANSWER:"""

    def build_top_issues_prompt(self, rows, start_year=None, end_year=None) -> str:
        date_range_str = f"({start_year or '2008'} to {end_year or '2026'})"
        
        data_summary = ""
        for idx, r in enumerate(rows, 1):
            data_summary += f"{idx}. Issue Category: {r['issue_type']} | Topic: {r['topic_name']} | Total Mentions: {r['mention_count']} (Active: {r['earliest_date']} to {r['latest_date']})\n"

        return f"""You are an expert municipal analyst for the City of Sheffield Lake.
Below is exact database aggregation data showing the most frequently discussed issues in city council and board meetings {date_range_str}.

AGGREGATED DATABASE DATA:
{data_summary}

TASK:
Summarize these top municipal issues into an executive briefing for city leaders. 
Group related topics where appropriate, highlight the highest-priority concerns based on mention counts, and note the date spans. Do NOT invent any facts or numbers not provided in the data.

EXECUTIVE BRIEFING:"""

    def generate_ollama_response(self, prompt: str, model_name: str = "llama3"):
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model_name, "prompt": prompt, "stream": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        print(chunk.get("response", ""), end="", flush=True)
            print()
        except Exception as e:
            print(f"\n[Error calling Ollama]: {e}")

def print_banner():
    print("\n" + "=" * 65)
    print("   CITY OF SHEFFIELD LAKE - SQLITE FTS5 RAG SYSTEM")
    print("   Database: SQLite FTS5 | Years: 2008–2026")
    print("=" * 65)
    print(" Commands:")
    print("   /top [N]                  - Get top N overall issues via SQL count")
    print("   /issues                   - Data Check: Print distinct issue types & topics")
    print("   /schema                   - Data Check: Display tables, columns & row counts")
    print("   /year <YYYY> or <YYYY-YYYY> - Set year or year range")
    print("   /category <Name>          - Filter by category")
    print("   /model <Name>             - Set Ollama model (default: llama3)")
    print("   /chunks <N>               - Set number of retrieved records")
    print("   /clear                    - Reset active filters")
    print("   exit OR quit              - Exit application")
    print("=" * 65 + "\n")

def run_cli():
    print_banner()
    rag = SQLiteRAGChain()

    start_year = None
    end_year = None
    category_filter = None
    model_name = "llama3"
    n_results = 5

    while True:
        try:
            filter_indicator = ""
            active = []
            if start_year or end_year:
                active.append(f"Years:{start_year or 'Min'}-{end_year or 'Max'}")
            if category_filter:
                active.append(f"Cat:{category_filter}")
            if active:
                filter_indicator = f" [{', '.join(active)}]"

            user_input = input(f"Sheffield-FTS{filter_indicator}> ").strip()
            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ["exit", "quit"]:
                print("\nExiting Sheffield Lake RAG CLI. Goodbye!")
                break

            elif cmd == "/clear":
                start_year = end_year = category_filter = None
                print(">>> Filters cleared.\n")
                continue

            elif cmd.startswith("/top"):
                parts = user_input.split(maxsplit=1)
                limit_val = 10
                if len(parts) > 1 and parts[1].isdigit():
                    limit_val = int(parts[1])

                start_time = time.perf_counter()
                rows = rag.retrieve_top_issues(
                    limit=limit_val,
                    start_year=start_year,
                    end_year=end_year,
                    category_filter=category_filter
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                print(f"\n[Aggregated top {len(rows)} topic cluster(s) from SQL in {elapsed_ms:.2f} ms]")
                if not rows:
                    print(">>> No records found for aggregation.\n")
                    continue

                # --- PRINT RAW SQL DATA BEFORE OLLAMA ---
                print("\n=================== RAW SQL RESULTS ===================")
                print(f"{'#':<3} | {'COUNT':<6} | {'DATE RANGE':<23} | {'ISSUE TYPE':<25} | {'TOPIC NAME'}")
                print("-" * 90)
                for idx, r in enumerate(rows, 1):
                    date_range = f"{r['earliest_date']} to {r['latest_date']}"
                    issue_type = (r['issue_type'][:22] + "...") if len(r['issue_type']) > 25 else r['issue_type']
                    print(f"{idx:<3} | {r['mention_count']:<6} | {date_range:<23} | {issue_type:<25} | {r['topic_name']}")
                print("=======================================================\n")
                
                print(f"[Generating AI executive briefing from top 10 SQL results using model: {model_name}...] \n" + "-" * 65 + "\n") 
                prompt = rag.build_top_issues_prompt(rows, start_year=start_year, end_year=end_year)
                rag.generate_ollama_response(prompt, model_name=model_name)
                print("-" * 65 + "\n")
                continue

            elif cmd == "/issues":
                rows = rag.get_all_distinct_issues()
                print(f"\n================ TOTAL DISTINCT ISSUES FOUND: {len(rows)} ================")
                print(f"{'#':<4} | {'ISSUE TYPE':<22} | {'COUNT':<6} | {'DATE RANGE':<23} | {'TOPIC NAME'}")
                print("-" * 90)
                for idx, r in enumerate(rows, 1):
                    date_range = f"{r['earliest_date']} to {r['latest_date']}"
                    issue_type = (r['issue_type'][:19] + "...") if len(r['issue_type']) > 22 else r['issue_type']
                    print(f"{idx:<4} | {issue_type:<22} | {r['mention_count']:<6} | {date_range:<23} | {r['topic_name']}")
                print("===================================================================\n")
                continue

            elif cmd == "/schema":
                schema = rag.get_database_schema()
                print("\n======================= SQLITE DATABASE SCHEMA =======================")
                for table_name, details in schema.items():
                    print(f"\nTABLE: {table_name} (Total Rows: {details['row_count']:,})")
                    print("-" * 55)
                    for col_name, col_type in details["columns"]:
                        print(f"  • {col_name:<30} {col_type}")
                print("======================================================================\n")
                continue

            elif cmd.startswith("/year"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    val = parts[1].strip()
                    if "-" in val:
                        s, e = val.split("-")
                        start_year, end_year = int(s), int(e)
                    else:
                        start_year = end_year = int(val)
                    print(f">>> Year filter set to: {start_year} to {end_year}\n")
                continue

            elif cmd.startswith("/category"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    category_filter = parts[1].strip()
                    print(f">>> Category filter set to: '{category_filter}'\n")
                continue

            elif cmd.startswith("/model"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    model_name = parts[1].strip()
                    print(f">>> Active model set to: '{model_name}'\n")
                continue

            elif cmd.startswith("/chunks"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1 and parts[1].isdigit():
                    n_results = int(parts[1])
                    print(f">>> Context chunks set to: {n_results}\n")
                continue

            # Execute Standard FTS Search
            start_time = time.perf_counter()
            rows = rag.retrieve_context(
                query=user_input, 
                limit=n_results, 
                start_year=start_year, 
                end_year=end_year, 
                category_filter=category_filter
            )
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            print(f"\n[Retrieved {len(rows)} record(s) in {elapsed_ms:.2f} ms]")
            if not rows:
                print(">>> No matching records found.\n")
                continue

            print(f"[Synthesizing answer with Ollama ({model_name})...]\n" + "-" * 65 + "\n")
            prompt = rag.build_prompt(user_input, rows)
            rag.generate_ollama_response(prompt, model_name=model_name)
            print("-" * 65 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

if __name__ == "__main__":
    run_cli()