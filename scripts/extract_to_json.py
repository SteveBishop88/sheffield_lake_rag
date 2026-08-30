#extracts json info from /data/staging_all_pdfs

import os
import sys
import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, List
import fitz  # PyMuPDF

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw_pdfs"
OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted_json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Logging Setup
LOG_FILE = PROJECT_ROOT / "extraction_errors.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3"

EXTRACTION_PROMPT_TEMPLATE = """You are an expert municipal records analyst for Sheffield Lake, Ohio.
Analyze the following text from meeting minutes and extract key structured information in STRICT JSON format.

Do not include any intro, markdown wrap-around text outside the json block, or prose. Return ONLY valid JSON matching this schema:

{{
  "meeting_date": "YYYY-MM-DD or Unknown",
  "category": "Safety | Council | Roads_Drains | Finance | General",
  "key_topics": [
    {{
      "topic_name": "Short label (e.g. Stormwater Drainage, Fire Truck Maintenance)",
      "description": "Brief 1-2 sentence summary of what was discussed or decided",
      "issue_type": "Infrastructure | Policy | Budget | Public Safety | Citizen Concern",
      "entities_involved": ["Names of council members, officials, or streets mentioned"]
    }}
  ],
  "action_items_or_votes": ["Brief list of official votes, resolutions, or direct actions taken"]
}}

TEXT TO ANALYZE:
{page_text}
"""

def extract_json_from_text(text: str, retries: int = 2) -> Dict[str, Any]:
    """Call Ollama to convert raw meeting text into structured JSON."""
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(page_text=text[:3500])
    
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }
    
    for attempt in range(retries + 1):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("response", "{}")
            return json.loads(raw_response)
        except Exception as e:
            if attempt < retries:
                continue
            logging.error(f"Failed JSON generation after {retries} retries: {e}")
            return {}

def process_pdf(pdf_path: Path):
    """Process a single PDF and save extracted structured JSON."""
    json_out_path = OUTPUT_DIR / f"{pdf_path.stem}.json"
    
    if json_out_path.exists():
        return "skipped"

    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"

        if not full_text.strip():
            logging.error(f"PDF contains no extractable text: {pdf_path.name}")
            return "error"

        structured_data = extract_json_from_text(full_text)
        
        # Metadata enrichment
        structured_data["source_filename"] = pdf_path.name
        structured_data["page_count"] = len(doc)
        
        with open(json_out_path, "w", encoding="utf-8") as f:
            json.dump(structured_data, f, indent=2)
        
        return "success"
    except Exception as e:
        logging.error(f"Failed processing {pdf_path.name}: {e}")
        return "error"

def main():
    pdf_files = list(DATA_DIR.rglob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {DATA_DIR}.")
        return

    total = len(pdf_files)
    print(f"Found {total} PDF documents in {DATA_DIR}.")
    print(f"Output directory: {OUTPUT_DIR}\n")

    skipped = 0
    processed = 0
    errors = 0

    if HAS_TQDM:
        for pdf_path in tqdm(pdf_files, desc="Processing PDFs"):
            res = process_pdf(pdf_path)
            if res == "skipped":
                skipped += 1
            elif res == "success":
                processed += 1
            else:
                errors += 1
    else:
        for idx, pdf_path in enumerate(pdf_files, start=1):
            print(f"[{idx}/{total}] Processing: {pdf_path.name}...", end="", flush=True)
            res = process_pdf(pdf_path)
            if res == "skipped":
                print(" (Skipped - already exists)")
                skipped += 1
            elif res == "success":
                print(" (Done)")
                processed += 1
            else:
                print(" (Error)")
                errors += 1

    print(f"\nBatch processing complete!")
    print(f"Processed: {processed} | Skipped: {skipped} | Errors: {errors}")
    if errors > 0:
        print(f"Check {LOG_FILE} for details on failed files.")

if __name__ == "__main__":
    main()