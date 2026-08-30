Markdown

# Sheffield Lake Municipal Records RAG & Analytics Pipeline

An AI-driven data retrieval and analytical engine built to process, query, and analyze 18 years of municipal records (2008–2026) for the City of Sheffield Lake, Ohio.

## Current Project Status: Local Vector Search Engine (Phase 1 Complete)

The system currently operates as a local, pinpoint search and extraction engine. It ingests thousands of pages of meeting minutes, ordinances, resolutions, and municipal reports, indexing them into a persistent vector database for semantic query retrieval with dynamic, source-cited LLM generation.

### System Architecture
* **Ingestion & Parsing:** `PyMuPDF` extracting text, page bounds, and structural metadata across 5,303 indexed document pages.
* **Vector Store:** `ChromaDB` running locally with `all-MiniLM-L6-v2` dense vector embeddings.
* **Local Inference:** Local LLMs (`llama3`, `llama3.1`) hosted via Ollama (`localhost:11434`), streaming responses with direct PDF and page-number citations.
* **Pipeline Core (`rag_chain.py`):** Handles semantic retrieval, dynamic prompt injection, metadata-aware filtering, and token streaming.
* **Interactive CLI (`scripts/cli.py`):** Shell application providing real-time querying, dynamic metadata filtering (`/year`, `/category`), chunk size controls (`/chunks`), and model toggling (`/model`).

---

## Dataset Overview
* **Total Scope:** ~5,303 pages of historical municipal records.
* **Time Horizon:** 2008–2026.
* **Coverage:** 18 distinct municipal categories (e.g., Council, Safety, Finance, Ordinances, Zoning, Roads & Drains).

---

## Getting Started

### Prerequisites
1. **Python 3.11+**
2. **Ollama** running locally with `llama3` or `llama3.1` pulled:
   ```bash
   ollama pull llama3

Running the Interactive CLI Shell

Launch the command-line interface directly from the project root:
Bash

python scripts/cli.py

Available CLI Commands
Command	Usage	Description
/year	/year 2024	Restrict search context to records from a specific year.
/category	/category Safety	Filter vector retrieval by document category.
/model	/model llama3.1	Switch the active Ollama inference model on the fly.
/chunks	/chunks 5	Adjust the number (N) of retrieved context snippets passed to the LLM.
/status	/status	Print active filter settings, chunk limits, and loaded model.
/clear	/clear	Reset all year and category metadata filters.
/help	/help	Print the command menu.
exit / quit	exit	Terminate the interactive CLI session.
Future Roadmap: Macro-Analytical System (Phase 2)

While the current Phase 1 vector RAG architecture excels at pinpoint document lookups ("What was discussed in the March 2011 Safety meeting regarding flood damage?"), vector similarity search alone cannot perform global data synthesis or statistical counting across the full corpus ("Count all street repair requests over 18 years").

Next steps will focus on upgrading the system to a macro-analytical knowledge engine:

    Hybrid SQL + Vector Store (Structured + Unstructured):

        Extract key metadata fields (dates, ordinance numbers, vote pass/fail status, dollar amounts) into a lightweight SQLite database alongside ChromaDB.

        Enable text-to-SQL query generation for exact counts, aggregations, and multi-year numerical tracking.

    GraphRAG (Knowledge Graph Integration):

        Map recurring entities (Council Members, Contractors, Infrastructure Projects, Street Names) into an interconnected graph structure.

        Enable long-term relational analysis across 18 years of meeting minutes.

8/23/26 updates:
Stage,Tool / Script,Status,Results
1. Scraping & Audit,verify_scraper.py,Completed,"1,115 / 1,115 PDFs (100%)"
2. Map / Extract,extract_to_json.py,Completed,"1,097 JSONs generated"
3. Load & Index,load_to_sqlite.py,Completed,"1,097 records loaded into SQLite FTS5"
4. Reduce / Synthesize,reduce_topics.py,Completed,Executive Macro Report streamed

8/23/26 update cont:
## Hybrid Search Engine (SQLite FTS5 + Ollama RAG)

A deterministic, high-precision retrieval system for searching 18+ years of Sheffield Lake municipal records without the chunking artifacts or hallucination risks of pure vector search.

### Key Architecture
* **Deterministic Keyword Search:** SQLite FTS5 index delivers <3ms query performance over full meeting transcripts.
* **Natural Language Query Bridge:** Automated stop-word filtering strips conversational noise (e.g., *"Who was appointed to..."*) down to core search terms (`"appointed" AND "Planning"`).
* **Local LLM Synthesis:** Ollama (`llama3`) acts strictly as an automated clerk to format retrieved records into clear summaries with source citations.

### CLI Usage
```bash
python scripts/cli.py

/year 2021-2024 - Filter queries by year or range

/category "Work Session" - Target specific municipal meeting types

/chunks <N> - Control context depth passed to Ollama (default: 5)

/clear - Reset active search filters

***
