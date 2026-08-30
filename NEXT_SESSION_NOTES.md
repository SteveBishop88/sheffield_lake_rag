Project: City of Sheffield Lake Municipal Records RAG

Current Branch/State: Phase 1 Complete (Pinpoint RAG + CLI Operational)
1. Current State Summary

    Database: ChromaDB initialized in ./db/ with 5,303 indexed pages across 18 municipal categories (2008–2026).

    Pipeline: rag_chain.py extracts top N semantic vector matches via all-MiniLM-L6-v2, passes cited context blocks to Ollama (llama3 / llama3.1), and streams response tokens.

    Interface: scripts/cli.py delivers an interactive shell supporting live querying, model switching, chunk depth adjustments (/chunks), and metadata filtering (/year, /category).

    Key Finding: Standard vector search handles pinpoint lookup and exact excerpt extraction well, but fails at global macro-synthesis (e.g., counting, trend identification, or cross-corpus aggregation) due to the fixed chunk retrieval window (N snippets).

2. Architecture Goal for Phase 2

Transition the engine from a "pinpoint document lookup search engine" to a "macro-analytical municipal intelligence tool" by adding two complementary layers over the raw text corpus:

                      [ User Query ]
                            │
            ┌───────────────┼───────────────┐
            ▼               ▼               ▼
      [ Structured ]  [ Relational ]   [ Vector ]
       SQLite Engine    Graph Engine    ChromaDB
            │               │               │
  (Counts/Aggregations) (Entity Links) (Pinpoint Snippets)
            └───────────────┼───────────────┘
                            ▼
                    [ Final LLM Synthesis ]

3. Immediate Action Items for Next Session

    Hybrid SQL Layer (Structured Extraction)

        Goal: Allow exact counts, date range filters, and numerical aggregations.

        Task: Design a light schema (documents, ordinances, resolutions, votes) in SQLite.

        Implementation: Create a batch script using an LLM to parse raw PDFs into structured rows (e.g., ordinance_number, date, passed_bool, category, cost_estimate).

    GraphRAG Layer (Knowledge & Entity Graph)

        Goal: Track recurring entities and long-term project threads over 18 years.

        Task: Define key entity types (Person, Street/Location, Infrastructure Project, Contractor, Ordinance).

        Implementation: Build an entity-relation extractor script to map links (e.g., [Council Member X] -> VOTED_FOR -> [Resolution Y] -> AFFECTS -> [Lake Road Drainage Project]).

4. Quick Start Command for Next Time
Bash

# Launch current CLI to verify base environment
python scripts/cli.py