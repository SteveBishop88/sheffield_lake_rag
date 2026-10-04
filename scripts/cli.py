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
import urllib.error
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
                    if isinstance(meta, dict) and "rowid" in meta:
                        rowids_to_lookup.append(meta["rowid"])

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
                meeting_date = None
                if isinstance(chunk, dict):
                    meeting_date = chunk.get("meeting_date") or chunk.get("date")
                    if not meeting_date and "rowid" in chunk:
                        meeting_date = db_date_map.get(chunk["rowid"])
                elif isinstance(chunk, str):
                    match = re.search(r"\b(19|20)\d{2}\b", chunk)
                    if match:
                        meeting_date = match.group(0)

                parsed_year = None
                if meeting_date:
                    year_match = re.search(r"\b(19|20)\d{2}\b", str(meeting_date))
                    if year_match:
                        parsed_year = int(year_match.group(0))

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

    def handle_issues_command(self, start_year: int = None, end_year: int = None):
        """Executes a breakdown of all issue types in key_topics,
        respecting active date filters if set.
        """
        if not self.db_path.exists():
            print("\nDatabase file not found.\n")
            return

        params = []
        if start_year or end_year:
            sql = """
                SELECT k.issue_type, COUNT(*) as topic_count
                FROM key_topics k
                JOIN meetings m ON k.meeting_id = m.meeting_id
                WHERE k.issue_type IS NOT NULL AND k.issue_type != ''
            """
            if start_year and end_year:
                sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) BETWEEN ? AND ?"
                params.extend([start_year, end_year])
            elif start_year:
                sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) >= ?"
                params.append(start_year)
            elif end_year:
                sql += " AND CAST(strftime('%Y', m.meeting_date) AS INTEGER) <= ?"
                params.append(end_year)

            sql += " GROUP BY k.issue_type ORDER BY topic_count DESC;"
        else:
            sql = """
                SELECT issue_type, COUNT(*) as topic_count
                FROM key_topics
                WHERE issue_type IS NOT NULL AND issue_type != ''
                GROUP BY issue_type
                ORDER BY topic_count DESC;
            """

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            results = cursor.fetchall()

        if not results:
            print("\nNo issue types found for the given criteria.\n")
            return

        print("\n================== ISSUE TYPE BREAKDOWN ==================")
        print(f"{'Issue Type':<40} | {'Topics Count':<12}")
        print("-" * 57)
        for issue_type, count in results:
            print(f"{issue_type:<40} | {count:<12}")
        print("==========================================================\n")

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

    def retrieve_top_issues(self, limit: int = 10, start_year: int = None, end_year: int = None, meeting_type_filter: str = None):
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
            JOIN meetings m ON fts.rowid = m.meeting_id
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

        if meeting_type_filter:
            sql += " AND LOWER(m.meeting_type) LIKE ?"
            params.append(f"%{meeting_type_filter.lower()}%")

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

    def generate_sql_query(self, user_query: str, limit: int = 20, start_year: int = None, end_year: int = None, meeting_type_filter: str = None, model_name: str = "llama3") -> str:
        """Uses Ollama to translate natural language into a single executable SQL query."""
        filter_context = []
        if start_year and end_year:
            filter_context.append(f"CAST(strftime('%Y', m.meeting_date) AS INTEGER) BETWEEN {start_year} AND {end_year}")
        elif start_year:
            filter_context.append(f"CAST(strftime('%Y', m.meeting_date) AS INTEGER) >= {start_year}")
        elif end_year:
            filter_context.append(f"CAST(strftime('%Y', m.meeting_date) AS INTEGER) <= {end_year}")

        if meeting_type_filter:
            clean_cat = meeting_type_filter.strip("'\"").lower()
            filter_context.append(f"LOWER(m.meeting_type) LIKE '%{clean_cat}%'")

        filter_clause = (" AND " + " AND ".join(filter_context)) if filter_context else ""

        schema_json = json.dumps(self.get_database_schema(), indent=2)

        prompt = f"""You are an expert SQLite generator for a municipal meeting database.
Convert the user's natural language question into a single valid SQLite query.

DATABASE SCHEMA:
{schema_json}

STRICT SQLITE & FTS5 RULES (DO NOT VIOLATE):
1. NEVER use EXTRACT(YEAR FROM ...). SQLite DOES NOT support EXTRACT(). Always use CAST(strftime('%Y', m.meeting_date) AS INTEGER) for years.
2. NEVER select ft.match_score or ft.matched_values. Standard SQLite FTS tables ONLY contain the indexed text columns and rowid.
3. FTS MATCH SYNTAX: Always match against the table name directly: `meetings_fts MATCH 'roads OR drainage'`
4. Always JOIN using: `FROM meetings m JOIN meetings_fts fts ON m.meeting_id = fts.rowid`
5. Wrap multiple search predicates in explicit parentheses when combining with AND/date constraints.
6. Active constraints (ALWAYS include these if non-empty): {filter_clause if filter_clause else 'None'}
7. Always include `LIMIT {limit}` at the end of the query.
8. Unless an active year filter is set or the user explicitly specifies a year/date in their query, DO NOT add year constraints (m.meeting_date LIKE ...) to the WHERE clause.

CRITICAL FTS SYNTAX RULES:

1. NEVER put fts.match in a SELECT statement. MATCH is NOT a column.
2. NEVER use functional syntax like ft.match('query', 'table').
3. ALWAYS use the infix syntax in the WHERE clause: meetings_fts MATCH 'term1 OR term2'
4. To select the matched topic or column text, select the actual column names (e.g., fts.topic_name, fts.issue_type, fts.description).

Output ONLY raw executable SQL starting with SELECT or WITH. Do NOT include markdown backticks or prose.

User Question: {user_query}

SQLite Query:"""

        req_data = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 4096}
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(req_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                raw_text = res.get("response", "").strip()

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
        # Deduplicate overlapping references between SQL rows and vector chunks
        seen_rowids = set()
        dedup_rows = []
        for r in (rows or []):
            try:
                r_id = r["meeting_id"] if "meeting_id" in r.keys() else r["rowid"]
                if r_id in seen_rowids:
                    continue
                seen_rowids.add(r_id)
            except (KeyError, IndexError):
                pass
            dedup_rows.append(r)

        dedup_chunks = []
        for c in (vector_chunks or []):
            if isinstance(c, dict) and "rowid" in c:
                if c["rowid"] in seen_rowids:
                    continue
                seen_rowids.add(c["rowid"])
            dedup_chunks.append(c)

        results_preview = []
        for r in dedup_rows[:20]:
            row_dict = {col: r[col] for col in col_names}
            results_preview.append(str(row_dict))

        data_str = "\n".join(results_preview) if results_preview else "No matching structured SQL rows returned."
        total_rows = len(dedup_rows)

        vector_context_str = ""
        if dedup_chunks:
            chunk_texts = [f"- {c.get('text', str(c)) if isinstance(c, dict) else str(c)}" for c in dedup_chunks]
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

        req_data = {
            "model": model_name,
            "prompt": prompt,
            "stream": True,
            "options": {"num_ctx": 4096}
        }
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(req_data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        print(chunk.get("response", ""), end="", flush=True)
            print()
        except urllib.error.URLError as e:
            print(f"\n[Error: Could not connect to Ollama at localhost:11434]: {e}")
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
    print("   /year <YYYY|YYYY-YYYY>    - Filter by year or year range (e.g. /year 2020-2024)")
    print("   /type or /meeting_type    - Filter by meeting/committee type (e.g. /type Safety)")
    print("                               Valid Types: Council, Safety, Roads_Drains, Finance,")
    print("                                            Buildings_Lands, Ordinance, Planning, Zoning,")
    print("                                            Administration, Public Works, Community Center, Park Board")
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
    meeting_type_filter = None
    model_name = "llama3"
    n_results = 5

    while True:
        try:
            active = []
            if start_year or end_year:
                active.append(f"Years:{start_year or 'Min'}-{end_year or 'Max'}")
            if meeting_type_filter:
                active.append(f"Type:{meeting_type_filter}")
            filter_indicator = f" [{', '.join(active)}]" if active else ""

            user_input = input(f"Sheffield-SQL{filter_indicator}> ").strip()
            if not user_input:
                continue

            cmd = user_input.lower()
            if cmd in ["exit", "quit"]:
                print("\nExiting Sheffield Lake SQL CLI. Goodbye!")
                break

            elif cmd == "/clear":
                start_year = end_year = meeting_type_filter = None
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
                    meeting_type_filter=meeting_type_filter,
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
                sql_chain.handle_issues_command(start_year=start_year, end_year=end_year)
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

            elif cmd.startswith("/meeting_type") or cmd.startswith("/type"):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    meeting_type_filter = parts[1].strip().strip("'\"")
                    print(f">>> meeting_type filter set to: '{meeting_type_filter}'\n")
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
                /meeting_type "Name"    : Filter by meeting_type (e.g., /meeting_type "Work Session")
                VALID MEETING TYPES TO QUERY:
                • Council
                • Safety
                • Roads_Drains
                • Buildings_Lands
                • Finance
                • Ordinance
                • Planning
                • Zoning
                • Administration
                • Public Works
                • Community Center
                • Park Board

                QUERY GENERATION RULES FOR `meeting_type`:
                - ALWAYS use `LOWER(m.meeting_type) LIKE '%<clean_keyword>%'` when filtering by meeting_type.
                - REASON: DB records frequently contain compound pipe-delimited values (e.g. 'Safety | Council | Roads_Drains'). Exact equality (=) will fail.
                
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
                cat_str = meeting_type_filter if meeting_type_filter else "None (All Categories)"

                status_output = f"""
                    ===================================================================
                                                CURRENT CLI STATUS
                    ===================================================================
                    Active Year Filter     : {year_str}
                    Active meeting_type Filter : {cat_str}
                    Result Limit (/chunks) : {n_results}
                    Ollama Model           : {model_name}
                    Vector Index Loaded    : {'Yes' if sql_chain.vector_index else 'No (SQL only)'}
                    ===================================================================
                    """
                print(textwrap.dedent(status_output).strip())
                print()
                continue

            start_time = time.perf_counter()
            sql_query = sql_chain.generate_sql_query(
                user_query=user_input,
                limit=n_results,
                start_year=start_year,
                end_year=end_year,
                meeting_type_filter=meeting_type_filter,
                model_name=model_name,
            )

            col_names, rows = [], []
            if sql_query:
                print(f"\n[Generated SQL]: {sql_query}")
                col_names, rows = sql_chain.execute_sql(sql_query)
            else:
                print(">>> Could not generate SQL query; falling back entirely to vector search.\n")

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