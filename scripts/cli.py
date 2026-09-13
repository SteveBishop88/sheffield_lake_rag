# Interactive Text-to-SQL + RAG Hybrid CLI for Sheffield Lake Municipal Records (2008–2026)

import os
import certifi

# Fix SSL / Hugging Face cache lookup issue on Windows
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import json
import re
import sqlite3
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

# Optional vector search dependencies (graceful fallback if not installed/indexed yet)
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import faiss
    HAS_VECTOR_LIBS = True
except ImportError:
    HAS_VECTOR_LIBS = False

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"
VECTOR_INDEX_PATH = PROJECT_ROOT / "db" / "faiss_index.bin"
VECTOR_METADATA_PATH = PROJECT_ROOT / "db" / "vector_metadata.json"


class SheffieldSQLChain:

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.embedder = None
        self.vector_index = None
        self.vector_metadata = []

        # Initialize vector store if available
        if HAS_VECTOR_LIBS and VECTOR_INDEX_PATH.exists() and VECTOR_METADATA_PATH.exists():
            try:
                self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
                self.vector_index = faiss.read_index(str(VECTOR_INDEX_PATH))
                with open(VECTOR_METADATA_PATH, "r", encoding="utf-8") as f:
                    self.vector_metadata = json.load(f)
            except Exception as e:
                print(f"[Warning: Could not load vector index]: {e}")

    def retrieve_vector_chunks(
        self,
        query: str,
        top_k: int = 5,
        start_year: int = None,
        end_year: int = None,
        oversample_factor: int = 5,
    ):
        """Retrieves semantically relevant unstructured text chunks using FAISS,

        applying post-filtering metadata checks for active CLI year ranges.
        """
        if not (self.embedder and self.vector_index and self.vector_metadata):
            return []

        try:
            has_year_filter = start_year is not None or end_year is not None
            fetch_k = top_k * oversample_factor if has_year_filter else top_k

            query_vector = self.embedder.encode([query]).astype("float32")
            distances, indices = self.vector_index.search(query_vector, fetch_k)

            candidate_chunks = []
            rowids_to_lookup = []

            for idx in indices[0]:
                if 0 <= idx < len(self.vector_metadata):
                    meta = self.vector_metadata[idx]
                    candidate_chunks.append(meta)
                    # Track rowid or id for SQLite metadata fallback if year is missing in JSON
                    if isinstance(meta, dict) and "rowid" in meta:
                        rowids_to_lookup.append(meta["rowid"])

            # Map SQLite meeting dates if vector metadata doesn't contain explicit parsed years
            db_date_map = {}
            if rowids_to_lookup and self.db_path.exists():
                placeholders = ",".join("?" for _ in rowids_to_lookup)
                sql = f"SELECT rowid, meeting_date FROM meetings WHERE rowid IN ({placeholders})"
                try:
                    with sqlite3.connect(self.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute(sql, rowids_to_lookup)
                        for r_id, m_date in cursor.fetchall():
                            db_date_map[r_id] = m_date
                except Exception:
                    pass

            filtered_results = []
            for chunk in candidate_chunks:
                # Resolve date string from chunk dict or SQLite fallback
                meeting_date = None
                if isinstance(chunk, dict):
                    meeting_date = chunk.get("meeting_date") or chunk.get("date")
                    if not meeting_date and "rowid" in chunk:
                        meeting_date = db_date_map.get(chunk["rowid"])
                elif isinstance(chunk, str):
                    match = re.search(r"\b(19|20)\d{2}\b", chunk)
                    if match:
                        meeting_date = match.group(0)

                # Parse numeric year
                parsed_year = None
                if meeting_date:
                    year_match = re.search(r"\b(19|20)\d{2}\b", str(meeting_date))
                    if year_match:
                        parsed_year = int(year_match.group(0))

                # Apply post-filtering criteria
                if parsed_year is not None:
                    if start_year and parsed_year < start_year:
                        continue
                    if end_year and parsed_year > end_year:
                        continue

                filtered_results.append(chunk)

                if len(filtered_results) == top_k:
                    break

            return filtered_results
        except Exception as e:
            print(f"\n[Warning: Vector retrieval failed]: {e}")
            return []

    def get_all_distinct_issues(self):
        if not self.db_path.exists():
            return []

        sql = """
            SELECT 
                fts.issue_type,
                COUNT(*) as mention_count,
                COALESCE(MIN(NULLIF(m.meeting_date, '')), 'Unknown') as earliest_date,
                COALESCE(MAX(NULLIF(m.meeting_date, '')), 'Unknown') as latest_date,
                fts.topic_name AS topic_name
            FROM meetings_fts fts
            JOIN meetings m ON fts.rowid = m.rowid
            WHERE fts.issue_type IS NOT NULL AND fts.issue_type != ''
            GROUP BY fts.issue_type, fts.topic_name
            ORDER BY mention_count DESC, fts.issue_type ASC
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            return cursor.fetchall()

    def get_database_schema(self):
        if not self.db_path.exists():
            return {}

        schema_info = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]

            for table in tables:
                safe_table = f'"{table}"'
                cursor.execute(f"PRAGMA table_info({safe_table});")
                columns = [(row[1], row[2]) for row in cursor.fetchall()]

                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {safe_table};")
                    row_count = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    row_count = 0

                schema_info[table] = {"columns": columns, "row_count": row_count}

        return schema_info

    def retrieve_top_issues(self, limit: int = 10, start_year: int = None, end_year: int = None, category_filter: str = None):
        if not self.db_path.exists():
            return []

        sql = """
            SELECT 
                fts.issue_type,
                fts.topic_name,
                COUNT(*) as mention_count,
                MIN(m.meeting_date) as earliest_date,
                MAX(m.meeting_date) as latest_date
            FROM meetings_fts fts
            JOIN meetings m ON fts.rowid = m.rowid
            WHERE fts.issue_type IS NOT NULL AND fts.issue_type != ''
        """
        params = []

        if start_year and end_year:
            sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) BETWEEN ? AND ?"
            params.extend([start_year, end_year])
        elif start_year:
            sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) >= ?"
            params.append(start_year)
        elif end_year:
            sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) <= ?"
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

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()

    def generate_sql_query(self, user_query: str, limit: int = 20, start_year: int = None, end_year: int = None, category_filter: str = None, model_name: str = "llama3") -> str:
        """Uses Ollama to translate natural language into a single executable SQL query."""
        filter_context = []
        if start_year and end_year:
            filter_context.append(f"m.meeting_date BETWEEN '{start_year}-01-01' AND '{end_year}-12-31'")
        elif start_year:
            filter_context.append(f"m.meeting_date >= '{start_year}-01-01'")
        elif end_year:
            filter_context.append(f"m.meeting_date <= '{end_year}-12-31'")

        if category_filter:
            filter_context.append(f"m.category LIKE '%{category_filter}%'")

        filter_clause = (" AND " + " AND ".join(filter_context)) if filter_context else ""

        prompt = f"""You are an expert SQLite generator for a municipal meeting database.
Convert the user's natural language question into a single valid SQLite query.

DATABASE SCHEMA:
- Table 'meetings' (m): rowid, meeting_id, source_filename, meeting_date, category
- Virtual Table 'meetings_fts' (fts): rowid, topic_name, description, issue_type

CRITICAL SQL & FTS5 RULES:
1. Always JOIN using: `FROM meetings m JOIN meetings_fts fts ON m.rowid = fts.rowid`
2. For FTS full-text searches, match on the virtual table directly: `meetings_fts MATCH 'term*'`
   NEVER write column-level match like `fts.topic_name MATCH`. Use `meetings_fts MATCH 'term*'` or `LIKE '%term%'`.
3. Wrap multiple OR search predicates in explicit parentheses when combining with AND/date constraints:
   Example: `WHERE (fts.topic_name LIKE '%barking%' OR fts.description LIKE '%barking%'){filter_clause}`
4. Active date/category constraints (ALWAYS include these if non-empty): {filter_clause if filter_clause else 'None'}
5. Always include `LIMIT {limit}` at the end of the query to constrain results.

Output ONLY raw executable SQL starting with SELECT or WITH. Do NOT include markdown backticks or prose.

User Question: {user_query}

SQLite Query:"""

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model_name, "prompt": prompt, "stream": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                raw_text = res.get("response", "").strip()

                # Extract pure SQL block if wrapped in markdown code fence
                sql_match = re.search(r"```(?:sql)?\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
                if sql_match:
                    sql_str = sql_match.group(1).strip()
                else:
                    match_start = re.search(r"\b(SELECT|WITH)\b", raw_text, re.IGNORECASE)
                    if match_start:
                        sql_str = raw_text[match_start.start():].strip()
                    else:
                        sql_str = raw_text.strip()

                if ";" in sql_str:
                    sql_str = sql_str.split(";")[0]

                sql_str = sql_str.rstrip("`'\" ").strip()

                # Fix FTS match syntax errors generated by models
                sql_str = re.sub(r"\bfts\.\w+\s+MATCH\b", "meetings_fts MATCH", sql_str, flags=re.IGNORECASE)
                sql_str = re.sub(r"\bfts\s+MATCH\b", "meetings_fts MATCH", sql_str, flags=re.IGNORECASE)

                if sql_str.count("'") % 2 != 0:
                    sql_str += "'"

                sql_str += ";"
                return sql_str
        except Exception as e:
            print(f"\n[Warning: Ollama SQL generation failed]: {e}")
            return ""

    def execute_sql(self, sql_query: str):
        if not self.db_path.exists() or not sql_query:
            return None, []

        if sql_query.count("'") % 2 != 0:
            sql_query += "'"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute(sql_query)
                rows = cursor.fetchall()
                col_names = [description[0] for description in cursor.description] if cursor.description else []
                return col_names, rows
            except sqlite3.OperationalError as e:
                print(f"\n[SQLite Execution Error]: {e}")
                return None, []

    def synthesize_answer(self, user_query: str, sql_query: str, col_names: list, rows: list, vector_chunks: list = None, model_name: str = "llama3"):
        results_preview = []
        for r in (rows or [])[:20]:
            row_dict = {col: r[col] for col in col_names}
            results_preview.append(str(row_dict))

        data_str = "\n".join(results_preview) if results_preview else "No matching structured SQL rows returned."
        total_rows = len(rows) if rows else 0

        vector_context_str = ""
        if vector_chunks:
            chunk_texts = [f"- {c.get('text', str(c)) if isinstance(c, dict) else str(c)}" for c in vector_chunks]
            vector_context_str = "\n\nRetrieved Unstructured Vector Context (RAG):\n" + "\n".join(chunk_texts)

        prompt = f"""You are an expert municipal analyst for the City of Sheffield Lake.
Answer the user's question directly based on the provided SQL query results and retrieved unstructured vector context.

Executed SQL Query:
{sql_query}

Showing top {len(results_preview)} rows (out of {total_rows} total matching records):

SQL Query Result Data:
{data_str}{vector_context_str}

User Question: {user_query}

Answer:"""

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model_name, "prompt": prompt, "stream": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        print(chunk.get("response", ""), end="", flush=True)
            print()
        except Exception as e:
            print(f"\n[Error calling Ollama synthesis]: {e}")


def print_banner():
    print("\n" + "=" * 65)
    print("   CITY OF SHEFFIELD LAKE - TEXT-TO-SQL + RAG ENGINE")
    print("   Database: SQLite + FTS5 + FAISS Vector Index | Years: 2008–2026")
    print("=" * 65)
    print(" Commands:")
    print("   /top [N]                  - Get top N overall issues via SQL count")
    print("   /issues                   - Data Check: Print distinct issue types & topics")
    print("   /schema                   - Data Check: Display tables, columns & row counts")
    print("   /year <YYYY> or <YYYY-YYYY> - Set year or year range")
    print("   /category <Name>          - Filter by category")
    print("   /model <Name>             - Set Ollama model (default: llama3)")
    print("   /chunks <N>               - Set result limit for list queries")
    print("   /clear                    - Reset active filters")
    print("   /help                     - Show commands menu")
    print("   /status                   - Show current filters")
    print("   exit OR quit              - Exit application")
    print("=" * 65 + "\n")


def run_cli():
    print_banner()
    sql_chain = SheffieldSQLChain()

    start_year = None
    end_year = None
    category_filter = None
    model_name = "llama3"
    n_results = 5

    while True:
        try:
            active = []
            if start_year or end_year:
                active.append(f"Years:{start_year or 'Min'}-{end_year or 'Max'}")
            if category_filter:
                active.append(f"Cat:{category_filter}")
            filter_indicator = f" [{', '.join(active)}]" if active else ""

            user_input = input(f"Sheffield-SQL{filter_indicator}> ").strip()
            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ["exit", "quit"]:
                print("\nExiting Sheffield Lake SQL CLI. Goodbye!")
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
                rows = sql_chain.retrieve_top_issues(
                    limit=limit_val,
                    start_year=start_year,
                    end_year=end_year,
                    category_filter=category_filter,
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000

                print(f"\n[Aggregated top {len(rows)} topic cluster(s) from SQL in {elapsed_ms:.2f} ms]")
                if not rows:
                    print(">>> No records found for aggregation.\n")
                    continue

                print("\n=================== RAW SQL RESULTS ===================")
                print(f"{'#':<3} | {'COUNT':<6} | {'DATE RANGE':<23} | {'ISSUE TYPE':<25} | {'TOPIC NAME'}")
                print("-" * 90)
                for idx, r in enumerate(rows, 1):
                    date_range = f"{r['earliest_date']} to {r['latest_date']}"
                    issue_type = (r["issue_type"][:22] + "...") if len(r["issue_type"]) > 25 else r["issue_type"]
                    print(f"{idx:<3} | {r['mention_count']:<6} | {date_range:<23} | {issue_type:<25} | {r['topic_name']}")
                print("=======================================================\n")
                continue

            elif cmd == "/issues":
                rows = sql_chain.get_all_distinct_issues()
                print(f"\n================ TOTAL DISTINCT ISSUES FOUND: {len(rows)} ================")
                print(f"{'#':<4} | {'ISSUE TYPE':<22} | {'COUNT':<6} | {'DATE RANGE':<23} | {'TOPIC NAME'}")
                print("-" * 90)
                for idx, r in enumerate(rows, 1):
                    date_range = f"{r['earliest_date']} to {r['latest_date']}"
                    issue_type = (r["issue_type"][:19] + "...") if len(r["issue_type"]) > 22 else r["issue_type"]
                    print(f"{idx:<4} | {issue_type:<22} | {r['mention_count']:<6} | {date_range:<23} | {r['topic_name']}")
                print("===================================================================\n")
                continue

            elif cmd == "/schema":
                schema = sql_chain.get_database_schema()
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
                    print(f">>> Result limit set to: {n_results}\n")
                continue

            elif user_input == "/help":
                print("""
                CLI Command Reference:
                /year YYYY or YYYY-YYYY : Filter by year(s) (e.g., /year 2021-2024)
                /category "Name"        : Filter by category (e.g., /category "Work Session")
                /chunks N               : Set result limit for list queries (e.g., /chunks 5)
                /model model_name       : Change Ollama model (e.g., /model llama3)
                /schema                 : Show database tables and counts
                /issues                 : Show issue types and topics
                /top [N]                : Show top N topic clusters
                /status                 : View active filters and settings
                /clear                  : Clear all filters
                /help                   : Show this menu
                exit / quit             : Exit CLI
                            """)
                continue

            elif cmd == "/status":
                year_str = f"{start_year}-{end_year}" if start_year and end_year else (str(start_year) if start_year else "None (All Years)")
                cat_str = category_filter if category_filter else "None (All Categories)"

                status_output = f"""
                    ===================================================================
                                                CURRENT CLI STATUS
                    ===================================================================
                    Active Year Filter     : {year_str}
                    Active Category Filter : {cat_str}
                    Result Limit (/chunks) : {n_results}
                    Ollama Model           : {model_name}
                    Vector Index Loaded    : {'Yes' if sql_chain.vector_index else 'No (SQL only)'}
                    ===================================================================
                    """
                print(textwrap.dedent(status_output).strip())
                print()
                continue

            # Hybrid Execution Step 1: Text-to-SQL + Vector Search Concurrent Execution
            start_time = time.perf_counter()
            sql_query = sql_chain.generate_sql_query(
                user_query=user_input,
                limit=n_results,
                start_year=start_year,
                end_year=end_year,
                category_filter=category_filter,
                model_name=model_name,
            )

            col_names, rows = [], []
            if sql_query:
                print(f"\n[Generated SQL]: {sql_query}")
                col_names, rows = sql_chain.execute_sql(sql_query)
            else:
                print(">>> Could not generate SQL query; falling back entirely to vector search.\n")

            # Always-On Vector Search Retrieval with active year post-filtering
            vector_chunks = sql_chain.retrieve_vector_chunks(
                query=user_input,
                top_k=n_results,
                start_year=start_year,
                end_year=end_year,
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            year_filter_str = f" (Filtered: {start_year or 'Min'}–{end_year or 'Max'})" if (start_year or end_year) else ""
            print(f"[Executed in {elapsed_ms:.2f} ms | Returned {len(rows or [])} SQL row(s) & {len(vector_chunks)} vector chunk(s){year_filter_str}]")
            print("-" * 65)

            if rows or vector_chunks:
                sql_chain.synthesize_answer(
                    user_query=user_input,
                    sql_query=sql_query or "N/A",
                    col_names=col_names,
                    rows=rows or [],
                    vector_chunks=vector_chunks,
                    model_name=model_name,
                )
            else:
                print("No relevant information found across structured database or vector index.")

            print("-" * 65 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break


if __name__ == "__main__":
    run_cli()