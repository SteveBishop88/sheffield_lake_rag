# Sheffield Lake Municipal Records RAG & Analytics Pipeline

An AI-driven hybrid retrieval and analytical engine built to process, index, query, and synthesize 18 years of municipal meeting records (2008–2026) for the City of Sheffield Lake, Ohio.

## System Overview

The system operates as a hybrid **Text-to-SQL + Vector RAG pipeline**, bringing together deterministic SQL analytics and semantic vector search. By combining an **SQLite FTS5 full-text index**, dense **FAISS vector embeddings**, and local **Ollama LLM synthesis**, it supports precise SQL scalar aggregations, multi-year trend tracking, and deep semantic retrieval over municipal meeting minutes with direct source citations.

---

## Data Pipeline Architecture

[Target Year Pages] ──> [Scraper] ──> [Raw PDFs] ──> [JSON Extraction] ──> [Data Cleaning] ──> [SQLite DB + FTS5] ──> [FAISS Vector Store] ──> [Text-to-SQL + RAG Workspace]
### 1. Robust Web Scraping (`scripts/scraper.py` / `scripts/scraper2.py`)
* **Target Array Architecture:** Eliminates crawler drift by mapping explicit multi-year landing pages (`2008-minutes` through `2026-minutes`).
* **Two-Stage Fetch Pipeline:** Handles irregular WordPress structures by resolving direct `.pdf` links as well as intermediate HTML subpages containing embedded PDFs.
* **Inclusion/Exclusion Filtering:** Restricts collection strictly to municipal meeting types while automatically excluding administrative forms, permits, and external domain links.

### 2. Structured Extraction (`scripts/extract_to_json.py`)
* Parses raw PDF files into structured JSON documents containing metadata (meeting date, department/committee category, file path) and normalized full text.

### 3. Data Normalization (`scripts/clean_dates.py` & `scripts/clean_issue_types.py`)
* Normalizes dates across varied historical record formats into standard ISO format (`YYYY-MM-DD`).
* Standardizes topic and issue classifications to eliminate naming redundancies across multi-year dataset imports.

### 4. High-Performance Indexing (`scripts/load_to_sqlite.py` & `scripts/build_fts_index.py`)
* Ingests parsed and cleaned JSON data into a lightweight SQLite database (`meetings` table).
* Constructs a dedicated **FTS5 full-text search index** (`meetings_fts` table) supporting BM25 ranking across topics, descriptions, and issue types.

### 5. Hybrid Retrieval & Text-to-SQL Workspace (`scripts/cli.py`)
* **Text-to-SQL Engine:** Dynamically generates and executes structured SQL queries (handling aggregations, operator precedence, and explicit date filtering) to fetch exact numerical counts and tabular metrics.
* **Dense Vector Search (FAISS):** Retrieves semantic context chunks in parallel to handle unstructured queries and complement structured SQL output.
* **Source-Cited Generation:** Streams local Ollama LLM responses anchored strictly to retrieved structured records and vector search context.

---

## Pipeline Execution Order

To run or update the pipeline end-to-end, execute the scripts in the following sequential order:

```bash
# 1. Scrape raw municipal PDF records from the web
python scripts/scraper.py

# 2. Extract PDF text and metadata into JSON format
python scripts/extract_to_json.py

# 3. Clean and normalize extracted metadata (dates and issue categories)
python scripts/clean_dates.py
python scripts/clean_issue_types.py

# 4. Load normalized JSON records into SQLite
python scripts/load_to_sqlite.py

# 5. Build/rebuild the FTS5 full-text search index
python scripts/build_fts_index.py

# 6. Launch the interactive Text-to-SQL & RAG CLI workspace
python scripts/cli.py
Interactive CLI Workspace (scripts/cli.py)Launch the command-line workspace from the project root:Bashpython scripts/cli.py
CLI Command ReferenceCommandUsage ExampleDescription/year/year 2021 or /year 2016-2021Restrict SQL and Vector search context to a specific year or date range/category/category "Work Session"Filter search context by committee/department type/chunks/chunks 5Control the number ($N$) of retrieved document records passed to Ollama/model/model llama3.1Switch the active local Ollama inference model on the fly/schema/schemaDisplay table definitions and record counts for the SQLite database/issues/issuesInspect aggregated issue types and topic counts/top/topShow top issue clusters via aggregated SQL queries/status/statusView active filter settings, context limits, and active model/clear/clearReset active year and category metadata filters/help/helpDisplay the interactive command menuexit / quitexitTerminate the CLI sessionGetting StartedPrerequisitesPython 3.11+Ollama running locally with your model of choice pulled:Bashollama pull llama3.1
Setup InstructionsClone the Repository:Bashgit clone [https://github.com/SteveBishop88/sheffield_lake_rag.git](https://github.com/SteveBishop88/sheffield_lake_rag.git)
cd sheffield_lake_rag
Set Up Virtual Environment:Bashpython -m venv venv
source venv/Scripts/activate  # On Windows Git Bash
pip install -r requirements.txt
Run the Interactive CLI:Bashpython scripts/cli.py
Project Structuresheffield_lake_rag/
├── data/                    # Local data artifacts (ignored by Git)
│   ├── raw_pdfs/            # Downloaded municipal PDF records
│   ├── extracted_json/      # Structured JSON files
│   └── processed_json/      # Processed intermediate data
├── db/                      # Local SQLite databases (ignored by Git)
│   └── sheffield_lake_rag.db# SQLite FTS5 database & FAISS index storage
├── scripts/                 # Core pipeline codebase
│   ├── scraper.py           # Multi-year PDF scraper
│   ├── scraper2.py          # Secondary/fallback PDF scraper
│   ├── extract_to_json.py   # PDF text and metadata extraction
│   ├── clean_dates.py       # Date format normalization utility
│   ├── clean_issue_types.py # Topic and issue type cleaning utility
│   ├── load_to_sqlite.py    # SQLite database loader
│   ├── build_fts_index.py   # FTS5 virtual table indexer
│   ├── cli.py               # Main interactive shell and Text-to-SQL / RAG engine
│   ├── sql_data_check.py    # Quick SQL verification helper
│   ├── check_schema.py      # Standalone schema inspection helper
│   └── archive/             # Archived/legacy scripts (query_engine.py, reduce_topics.py, verify_scraper.py)
├── .gitignore               # Binary/data directory exclusions
├── requirements.txt         # Python dependencies
└── README.md                # Project documentation