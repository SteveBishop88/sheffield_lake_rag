# Sheffield Lake Municipal Records RAG & Analytics Pipeline

An AI-driven data retrieval and analytical engine built to process, index, query, and synthesize 18 years of municipal meeting records (2008–2026) for the City of Sheffield Lake, Ohio.

## System Overview

The system operates as a deterministic, high-precision retrieval and generation pipeline. It bypasses chunking artifacts and dense vector overhead by pairing an **SQLite FTS5 full-text search index** with **local Ollama LLM synthesis**. It enables pinpoint document lookups, multi-year chronological tracking, and macro-level topic synthesis over full meeting minutes with direct source citations.

---

## Data Pipeline Architecture

[Target Year Pages] ──> [Resilient Scraper] ──> [Raw PDFs] ──> [JSON Extraction] ──> [SQLite FTS5 DB] ──> [Ollama RAG CLI]
### 1. Robust Web Scraping (`scripts/scraper.py`)
* **Target Array Architecture:** Eliminates crawler drift by mapping explicit multi-year landing pages (`2008-minutes` through `2026-minutes`).
* **Two-Stage Fetch Pipeline:** Handles irregular WordPress structures by resolving both direct `.pdf` links and intermediate HTML subpages containing embedded PDFs.
* **Inclusion/Exclusion Filtering:** Restricts collection strictly to municipal meeting types while automatically excluding administrative forms, permits, and external domain links.

### 2. Structured Extraction (`scripts/extract_to_json.py`)
* Parses raw PDF files into structured JSON documents containing metadata (meeting date, department/committee category, file path) and normalized full text.

### 3. High-Performance Indexing (`scripts/load_to_sqlite.py` & `scripts/build_fts_index.py`)
* Ingests parsed JSON data into a lightweight SQLite database backed by an `FTS5` full-text search index.
* Delivers sub-3ms query performance across the entire 18-year record set.

### 4. Search & RAG Synthesis (`scripts/query_engine.py` & `scripts/rag_chain.py`)
* **Natural Language Query Bridge:** Converts conversational user prompts into optimized FTS5 match expressions by stripping stop words and applying implicit boolean operators.
* **Source-Cited Generation:** Streams local Ollama LLM (`llama3`, `llama3.1`) responses anchored strictly to retrieved search context, complete with document dates and categories.

---

## Pipeline Processing Status

| Stage | Script / Tool | Status | Results |
| :--- | :--- | :--- | :--- |
| **1. Scraping & Audit** | `scripts/scraper.py` | Completed | 1,115 / 1,115 PDFs fetched (100% target coverage) |
| **2. Map & Extract** | `scripts/extract_to_json.py` | Completed | 1,097 structured JSON documents generated |
| **3. Load & Index** | `scripts/load_to_sqlite.py` | Completed | 1,097 records indexed into SQLite FTS5 |
| **4. Synthesize** | `scripts/reduce_topics.py` | Completed | Executive macro-analytical summaries generated |

---

## Interactive CLI (`scripts/cli.py`)

Launch the command-line workspace from the project root:

```bash
python scripts/cli.py
CLI Command ReferenceCommandUsage ExampleDescription/year/year 2021 or /year 2021-2024Restrict search context to a specific year or range/category/category "Work Session"Filter search context by committee/department type/chunks/chunks 5Control the number ($N$) of retrieved document records passed to Ollama/model/model llama3.1Switch the active local Ollama inference model on the fly/status/statusView active filter settings, context limits, and active model/clear/clearReset active year and category metadata filters/help/helpDisplay the interactive command menuexit / quitexitTerminate the CLI sessionGetting StartedPrerequisitesPython 3.11+Ollama running locally with your model of choice pulled:Bashollama pull llama3.1
Setup InstructionsClone the Repository:Bashgit clone [https://github.com/SteveBishop88/sheffield_lake_rag.git](https://github.com/SteveBishop88/sheffield_lake_rag.git)
cd sheffield_lake_rag
Set Up Virtual Environment:Bashpython -m venv venv
source venv/Scripts/activate  # On Windows Git Bash
pip install -r requirements.txt
Run the Pipeline:Bash# Run the scraper to update raw PDFs
python scripts/scraper.py

# Extract text to JSON and index into SQLite
python scripts/extract_to_json.py
python scripts/load_to_sqlite.py

# Start querying
python scripts/cli.py
Project StructurePlaintextsheffield_lake_rag/
├── data/                      # Local data artifacts (ignored by Git)
│   ├── raw_pdfs/              # Downloaded municipal PDF records
│   ├── extracted_json/        # Structured JSON files
│   └── processed_json/        # Processed intermediate data
├── db/                        # Local SQLite databases (ignored by Git)
│   └── sheffield_lake.db      # SQLite FTS5 database
├── scripts/                   # Core pipeline codebase
│   ├── scraper.py             # Optimized multi-year PDF scraper
│   ├── extract_to_json.py     # PDF text and metadata extraction
│   ├── load_to_sqlite.py      # SQLite database loader
│   ├── build_fts_index.py     # FTS5 index construction
│   ├── query_engine.py        # FTS5 search execution and query parser
│   ├── rag_chain.py           # Ollama RAG integration & response streaming
│   ├── reduce_topics.py       # Macro synthesis and topic aggregation
│   └── cli.py                 # Interactive terminal shell
│   └── archive/               # Legacy/utility scripts
├── .gitignore                 # Binary/data directory exclusions
├── requirements.txt           # Python dependencies
└── README.md                  # Project documentation