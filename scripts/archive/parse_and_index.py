# 8/23/26 no longer used

# parses and indexes the files in the categorized_pdfs folder and creates 
# vector database.

import os
import re
from pathlib import Path
import pymupdf  # Modern import replacing deprecated 'fitz'
import chromadb
from chromadb.utils import embedding_functions

# Clean up broken SSL environment variable BEFORE importing HuggingFace/ChromaDB
if "SSL_CERT_FILE" in os.environ and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

# Silence Hugging Face symlink warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "categorized_pdfs"
CHROMA_DB_DIR = PROJECT_ROOT / "db"

def parse_filename_metadata(filename: str):
    """Extract year and category cleanly from standardized filenames, stopping before the date string."""
    match = re.match(
        r"^(\d{4})_([A-Za-z_]+?)_(?:January|February|March|April|May|June|July|August|September|October|November|December)",
        filename,
        re.IGNORECASE
    )
    if match:
        year, category = match.groups()
        return int(year), category.strip("_")
    
    fallback_match = re.match(r"^(\d{4})_([A-Za-z_]+)_(.*)\.pdf$", filename)
    if fallback_match:
        year, category, _ = fallback_match.groups()
        return int(year), category.rstrip("_")
        
    return None, "Uncategorized"

def process_and_index():
    # Clear invalid SSL environment variables if present
    if "SSL_CERT_FILE" in os.environ and not os.path.exists(os.environ["SSL_CERT_FILE"]):
        del os.environ["SSL_CERT_FILE"]

    # Initialize Persistent Chroma DB Client pointing to ./db
    chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
    
    # Sentence-transformers embedding function
    embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    
    collection = chroma_client.get_or_create_collection(
        name="sheffield_lake_minutes",
        embedding_function=embedding_func
    )

    pdf_files = list(DATA_DIR.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDFs ready for text extraction...")

    documents = []
    metadatas = []
    ids = []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        year, category = parse_filename_metadata(filename)

        try:
            doc = pymupdf.open(str(pdf_path))
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text").strip()

                if not text:
                    continue

                doc_id = f"{filename}_pg{page_num + 1}"
                
                documents.append(text)
                metadatas.append({
                    "filename": filename,
                    "year": year if year else 0,
                    "category": category,
                    "page": page_num + 1
                })
                ids.append(doc_id)

                # Batch upsert every 500 pages
                if len(documents) >= 500:
                    collection.add(documents=documents, metadatas=metadatas, ids=ids)
                    print(f"Indexed batch of {len(documents)} pages into ChromaDB...")
                    documents, metadatas, ids = [], [], []

        except Exception as e:
            print(f"Error reading {filename}: {e}")

    # Index remaining pages
    if documents:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        print(f"Indexed final batch of {len(documents)} pages.")

    print(f"\nSuccessfully indexed all documents into collection 'sheffield_lake_minutes' in ./db!")

if __name__ == "__main__":
    process_and_index()