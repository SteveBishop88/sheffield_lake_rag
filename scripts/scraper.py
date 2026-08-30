# scrapes data online for sheffield lake minutes
import os
import re
import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse
from pathlib import Path

# Suppress BS4 XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Setup Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DOWNLOAD_DIR = PROJECT_ROOT / "data" / "raw_pdfs"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

TARGET_PAGES = [
    "https://www.sheffieldlake.net/city-departments/council/2008-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2009-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/meeting-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2011-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2012-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2013-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2014-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2015-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2016-minutes-6/",
    "https://www.sheffieldlake.net/city-departments/council/2017-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2018-minutes-2/",
    "https://www.sheffieldlake.net/city-departments/council/2019-minutes/",
    "https://www.sheffieldlake.net/2020-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2021-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2022-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2023-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2024-minutes/",
    "https://www.sheffieldlake.net/2025-minutes/",
    "https://www.sheffieldlake.net/2026-minutes/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

MEETING_KEYWORDS = [
    "council", "minutes", "worksession", "committee", "agenda",
    "roads", "drains", "buildings", "lands", "finance", "safety", 
    "ordinance", "planning", "zba", "park", "hearing", "resolution"
]

IGNORE_TERMS = [
    "permit", "application", "contractor", "zoning-map", "banner",
    "food-truck", "backflow", "water-quality", "pws", "sewer-credit", 
    "pos-form", "master-plan", "vr_form", "history", "agreement", "rental",
    "ai1ec", "all-in-one-event-calendar", "feed", "plugin="
]

def get_soup(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"    [!] Error fetching page {url}: {e}")
        return None

def is_valid_meeting_pdf(pdf_url):
    parsed = urlparse(pdf_url)
    if "sheffieldlake.net" not in parsed.netloc:
        return False

    url_lower = pdf_url.lower()
    if any(term in url_lower for term in IGNORE_TERMS):
        return False
    if any(keyword in url_lower for keyword in MEETING_KEYWORDS):
        return True
    return False

def extract_pdf_from_url(target_url):
    clean_target = target_url.split('#')[0].rstrip('/')
    
    # Strictly require http or https protocols
    if not clean_target.startswith(("http://", "https://")):
        return None

    # Fast path: If direct PDF link, validate without extra web request
    if clean_target.lower().endswith(".pdf"):
        if is_valid_meeting_pdf(clean_target):
            return clean_target
        return None

    parsed = urlparse(clean_target)
    path_lower = parsed.path.lower()
    query_lower = parsed.query.lower()

    if "sheffieldlake.net" in parsed.netloc:
        if any(term in path_lower or term in query_lower for term in IGNORE_TERMS):
            return None
        
        # Only inspect subpages containing numbers (dates) or meeting keywords in path
        if not (re.search(r'\d', path_lower) or any(k in path_lower for k in MEETING_KEYWORDS)):
            return None

        soup = get_soup(clean_target)
        if not soup:
            return None
        
        for elem in soup.find_all(["a", "iframe", "embed"]):
            raw_href = elem.get("href") or elem.get("src")
            if raw_href:
                raw_href_clean = raw_href.strip()
                if raw_href_clean.lower().endswith(".pdf"):
                    full_pdf = urljoin(clean_target, raw_href_clean)
                    if full_pdf.startswith(("http://", "https://")) and is_valid_meeting_pdf(full_pdf):
                        return full_pdf
                
    return None

def extract_and_download_pdfs(subpage_urls):
    downloaded_count = 0
    skipped_count = 0
    processed_pdf_urls = set()

    for idx, page_url in enumerate(subpage_urls, start=1):
        print(f"[{idx}/{len(subpage_urls)}] Scanning landing page: {page_url}")
        soup = get_soup(page_url)
        if not soup:
            continue

        candidate_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "webcal:")):
                continue
            full_url = urljoin(page_url, href)
            
            if full_url.startswith(("http://", "https://")) and "sheffieldlake.net" in urlparse(full_url).netloc:
                candidate_links.append(full_url)

        for link_url in candidate_links:
            pdf_url = extract_pdf_from_url(link_url)
            
            if not pdf_url or pdf_url in processed_pdf_urls:
                continue

            processed_pdf_urls.add(pdf_url)

            clean_pdf_url = re.sub(r'^(https?://)+', 'https://', pdf_url, flags=re.IGNORECASE)
            filename = Path(urlparse(clean_pdf_url).path).name
            filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
            
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"

            local_path = DOWNLOAD_DIR / filename

            if local_path.exists():
                skipped_count += 1
                continue

            print(f"    [->] Downloading: {filename}")
            try:
                r = requests.get(clean_pdf_url, headers=HEADERS, timeout=20)
                r.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(r.content)
                downloaded_count += 1
            except Exception as e:
                print(f"    [!] Failed to download {clean_pdf_url}: {e}")

    print(f"\nScraping complete!")
    print(f"New Downloads: {downloaded_count} | Already Existing: {skipped_count}")

def main():
    print(f"[+] Direct scanning {len(TARGET_PAGES)} hand-verified landing pages...\n")
    extract_and_download_pdfs(TARGET_PAGES)

if __name__ == "__main__":
    main()