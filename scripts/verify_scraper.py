# quick verification audit that compares the actual PDF links found on 
# the website against what ended up in your data/raw_pdfs/ directory.


import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RAW_PDFS_DIR = PROJECT_ROOT / "data" / "raw_pdfs"

START_URL = "https://www.sheffieldlake.net/city-departments/council/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_soup(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[!] Error fetching {url}: {e}")
        return None

def verify_downloads():
    print("=" * 65)
    print("      SHEFFIELD LAKE PDF DOWNLOAD AUDIT & VERIFICATION")
    print("=" * 65)
    
    # 1. Gather all sub-pages from Council Hub
    print(f"\n[1/3] Mapping web pages starting from {START_URL}...")
    soup = get_soup(START_URL)
    if not soup:
        print("[!] Could not connect to site. Aborting audit.")
        return

    subpages = set([START_URL])
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(START_URL, href)
        parsed = urlparse(full_url)
        if "sheffieldlake.net" in parsed.netloc:
            path = parsed.path.lower()
            if any(term in path for term in ["council", "minutes", "worksession", "committee", "agenda", "20"]):
                if not path.endswith(".pdf"):
                    subpages.add(full_url)

    print(f"    -> Found {len(subpages)} sub-pages to inspect.")

    # 2. Extract every PDF URL from all sub-pages
    print("\n[2/3] Extracting PDF URLs across all sub-pages...")
    web_pdf_urls = set()
    for idx, page_url in enumerate(subpages, start=1):
        page_soup = get_soup(page_url)
        if not page_soup:
            continue
        for a in page_soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.lower().endswith(".pdf"):
                full_pdf_url = urljoin(page_url, href)
                # Fix malformed http://http:// typos from website HTML
                pdf_url = re.sub(
                    r"^(https?://)+",
                    "http://",
                    full_pdf_url,
                    flags=re.IGNORECASE,
                )
                web_pdf_urls.add(full_pdf_url)

    total_web_pdfs = len(web_pdf_urls)
    print(f"    -> Total distinct PDF links found on website: {total_web_pdfs}")

    # 3. Compare with local disk
    print("\n[3/3] Auditing against local 'data/raw_pdfs/' folder...")
    local_files = {f.name: f for f in RAW_PDFS_DIR.glob("*.pdf")}
    
    missing_files = []
    zero_byte_files = []
    verified_files = []

    for pdf_url in web_pdf_urls:
        raw_name = Path(urlparse(pdf_url).path).name
        sanitized_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', raw_name)
        
        if sanitized_name in local_files:
            local_path = local_files[sanitized_name]
            if local_path.stat().st_size == 0:
                zero_byte_files.append((sanitized_name, pdf_url))
            else:
                verified_files.append(sanitized_name)
        else:
            missing_files.append((sanitized_name, pdf_url))

    # Audit Summary
    print("\n" + "=" * 65)
    print("                    AUDIT SUMMARY RESULTS")
    print("=" * 65)
    print(f"  Total Unique PDFs on Site: {total_web_pdfs}")
    print(f"  Successfully Downloaded:   {len(verified_files)}")
    print(f"  Missing Files:             {len(missing_files)}")
    print(f"  Corrupted (0-byte) Files:  {len(zero_byte_files)}")
    print(f"  Total Local PDF Count:     {len(local_files)}")
    print("=" * 65)

    if missing_files:
        print("\n[!] MISSING FILES ON DISK:")
        for name, url in missing_files:
            print(f"  - {name} ({url})")

    if zero_byte_files:
        print("\n[!] CORRUPTED (0-BYTE) FILES:")
        for name, url in zero_byte_files:
            print(f"  - {name} ({url})")

    if not missing_files and not zero_byte_files:
        print("\n[✓] VERIFICATION SUCCESS: 100% of website PDFs are present and non-empty on disk!")

if __name__ == "__main__":
    verify_downloads()