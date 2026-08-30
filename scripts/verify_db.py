# does a quick sanity check that the vector db was created
# and returns some stats


import os

# Clean up broken SSL environment variable BEFORE importing HuggingFace/ChromaDB
if "SSL_CERT_FILE" in os.environ and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CHROMA_DB_DIR = PROJECT_ROOT / "db"

def verify_collection():
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    
    embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    
    collection = chroma_client.get_collection(
        name="sheffield_lake_minutes",
        embedding_function=embedding_func
    )

    total_count = collection.count()
    print(f"Collection 'sheffield_lake_minutes' total record count: {total_count}")

    # Inspect sample record
    sample = collection.peek(limit=1)
    if sample["ids"]:
        print(f"\nSample Record ID: {sample['ids'][0]}")
        print(f"Metadata: {sample['metadatas'][0]}")
        print(f"Text Snippet: {sample['documents'][0][:150]}...")

if __name__ == "__main__":
    verify_collection()