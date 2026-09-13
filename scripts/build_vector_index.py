import os
import certifi

# Fix invalid SSL_CERT_FILE path in environment
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

import sqlite3
import json
import os
import time
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# --- Configuration (matches cli.py) ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent  # Points to project root if script is inside /scripts

DB_PATH = PROJECT_ROOT / "db" / "sheffield_lake_rag.db"
INDEX_OUTPUT_PATH = PROJECT_ROOT / "db" / "faiss_index.bin"
META_OUTPUT_PATH = PROJECT_ROOT / "db" / "vector_metadata.json"
MODEL_NAME = "all-MiniLM-L6-v2"

# SQL Query matching your schema: key_topics joined with meetings
SQL_QUERY = """
SELECT 
    kt.topic_id,
    kt.topic_name,
    kt.description,
    kt.issue_type,
    m.meeting_id,
    m.meeting_date,
    m.category
FROM key_topics kt
JOIN meetings m ON kt.meeting_id = m.meeting_id
WHERE kt.description IS NOT NULL AND kt.description != '';
"""

def fetch_documents_from_sqlite(db_path: Path):
    """Fetches key_topics joined with meeting metadata from SQLite."""
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")

    print(f"Connecting to SQLite database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute(SQL_QUERY)
    rows = cursor.fetchall()
    conn.close()

    documents = []
    metadata = []

    for row in rows:
        topic_id, topic_name, description, issue_type, meeting_id, meeting_date, category = row
        
        # Format a comprehensive text block for embedding generation
        text_block = (
            f"Topic: {topic_name or 'N/A'}\n"
            f"Category: {category or 'N/A'}\n"
            f"Issue Type: {issue_type or 'N/A'}\n"
            f"Date: {meeting_date or 'N/A'}\n"
            f"Description: {description}"
        )
        
        documents.append(text_block)
        metadata.append({
            "topic_id": topic_id,
            "meeting_id": meeting_id,
            "topic_name": topic_name,
            "description": description,
            "issue_type": issue_type,
            "meeting_date": meeting_date,
            "category": category,
            "text": text_block
        })

    print(f"Retrieved {len(documents)} topic records for indexing.")
    return documents, metadata

def build_and_save_index():
    """Generates vector embeddings and saves FAISS index + metadata."""
    start_time = time.time()
    
    # 1. Fetch data
    documents, metadata = fetch_documents_from_sqlite(DB_PATH)
    if not documents:
        print("No documents found to index. Exiting.")
        return

    # 2. Load Embedding Model
    print(f"Loading SentenceTransformer model ('{MODEL_NAME}')...")
    model = SentenceTransformer(MODEL_NAME)

    # 3. Generate Embeddings
    print("Generating vector embeddings...")
    embeddings = model.encode(
        documents,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True  # Normalization enables Inner Product to act as Cosine Similarity
    )
    
    embeddings_np = np.array(embeddings).astype("float32")
    dimension = embeddings_np.shape[1]
    print(f"Generated embeddings shape: {embeddings_np.shape} (Dimension: {dimension})")

    # 4. Construct FAISS Index
    print("Building FAISS index...")
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings_np)

    # 5. Persist FAISS Index and Metadata
    faiss.write_index(index, str(INDEX_OUTPUT_PATH))
    print(f"FAISS index successfully saved to: {INDEX_OUTPUT_PATH}")

    with open(META_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"Vector metadata map successfully saved to: {META_OUTPUT_PATH}")

    elapsed = time.time() - start_time
    print(f"Done! Pipeline completed in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    build_and_save_index()