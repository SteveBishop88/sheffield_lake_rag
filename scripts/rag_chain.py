import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.utils import embedding_functions

# Unset invalid SSL vars if present
if "SSL_CERT_FILE" in os.environ and not os.path.exists(os.environ["SSL_CERT_FILE"]):
    del os.environ["SSL_CERT_FILE"]

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CHROMA_DB_DIR = PROJECT_ROOT / "db"

class SheffieldRAGChain:
    def __init__(self, collection_name: str = "sheffield_lake_minutes"):
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))
        self.embedding_func = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.collection = self.chroma_client.get_collection(
            name=collection_name,
            embedding_function=self.embedding_func
        )

    def retrieve_context(
        self, 
        query: str, 
        n_results: int = 5, 
        year_filter: Optional[int] = None, 
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant text chunks with metadata filters from ChromaDB."""
        where_clause = {}
        if year_filter and category_filter:
            where_clause = {"$and": [{"year": year_filter}, {"category": category_filter}]}
        elif year_filter:
            where_clause = {"year": year_filter}
        elif category_filter:
            where_clause = {"category": category_filter}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_clause if where_clause else None
        )

        retrieved_docs = []
        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                retrieved_docs.append({
                    "id": results['ids'][0][i],
                    "text": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i]
                })

        return retrieved_docs

    def build_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Format chunks into a structured prompt with strict citation constraints."""
        formatted_context = ""
        for idx, chunk in enumerate(context_chunks, 1):
            meta = chunk["metadata"]
            # Match the exact header style we want the LLM to write in citations
            formatted_context += (
                f"--- CHUNK [{idx}] ---\n"
                f"Document: {meta['filename']}\n"
                f"Page: {meta['page']}\n"
                f"Category: {meta['category']} | Year: {meta['year']}\n"
                f"Content:\n{chunk['text']}\n\n"
            )

        prompt = f"""You are an assistant for the City of Sheffield Lake, Ohio, analyzing municipal public records (2008–2026).

Answer the question accurately using ONLY the provided document context below. If the provided context does not contain sufficient information to answer, state clearly that the context does not contain the answer.

Always cite sources directly inline using the exact document filename and page number from the chunk header, like: [{context_chunks[0]['metadata']['filename']}, Page {context_chunks[0]['metadata']['page']}].

CONTEXT:
{formatted_context}

USER QUESTION:
{query}

ANSWER:"""
        return prompt

    def generate_ollama_response(self, prompt: str, model_name: str = "llama3") -> str:
        """Call a local Ollama instance with real-time streaming."""
        import requests
        import json
        
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": True  # Enable streaming
        }
        try:
            response = requests.post(url, json=payload, stream=True)
            response.raise_for_status()
            
            full_response = []
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode("utf-8"))
                    token = data.get("response", "")
                    print(token, end="", flush=True)  # Print tokens in real time
                    full_response.append(token)
            
            print("\n")  # Newline at completion
            return "".join(full_response)
        except Exception as e:
            return f"Error communicating with local Ollama instance: {e}"
    def ask(
        self, 
        query: str, 
        n_results: int = 5, 
        year_filter: Optional[int] = None, 
        category_filter: Optional[str] = None,
        use_llm: bool = False
    ) -> str:
        """End-to-end RAG execution: retrieve context, format prompt, and generate answer."""
        chunks = self.retrieve_context(
            query=query, 
            n_results=n_results, 
            year_filter=year_filter, 
            category_filter=category_filter
        )

        if not chunks:
            return "No matching municipal records found in the database."

        prompt = self.build_prompt(query, chunks)

        if use_llm:
            return self.generate_ollama_response(prompt)
        
        return prompt

if __name__ == "__main__":
    rag = SheffieldRAGChain()
    
    # Example: Run RAG pipeline retrieval and prompt construction
    sample_query = "What stormwater management and drainage repairs were discussed?"
    prompt_payload = rag.ask(sample_query, n_results=3, use_llm=False)
    
    print("================ GENERATED RAG PROMPT PAYLOAD ================")
    print(prompt_payload)