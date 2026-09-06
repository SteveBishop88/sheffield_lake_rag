# this scrapes a word press website and downloads pdfs based
# on id values given to the script.  It's not great but it works.
import os
import re
import requests
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse
from pathlib import Path

# Suppress BS4 XML parsing warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Paths relative to script location
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DOWNLOAD_DIR = PROJECT_ROOT / "data" / "raw_pdfs"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Full list of meeting minute years
TARGET_PAGES = [
    "https://www.sheffieldlake.net/city-departments/council/2008-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2009-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/meeting-minutes/", # 2010
    "https://www.sheffieldlake.net/city-departments/council/2011-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2012-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2013-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2014-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2015-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2016-minutes-6/",
    "https://www.sheffieldlake.net/city-departments/council/2017-minutes/",
    # "https://www.sheffieldlake.net/city-departments/council/2018-minutes-2/",
    # "https://www.sheffieldlake.net/city-departments/council/2019-minutes/",
    # "https://www.sheffieldlake.net/2020-minutes/",
    # "https://www.sheffieldlake.net/city-departments/council/2021-minutes/",
    # "https://www.sheffieldlake.net/city-departments/council/2022-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2023-minutes/",
    "https://www.sheffieldlake.net/city-departments/council/2024-minutes/",
    "https://www.sheffieldlake.net/2025-minutes/",
    "https://www.sheffieldlake.net/2026-minutes/"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

IGNORE_TERMS = [
    "permit", "application", "contractor", "zoning-map", "banner",
    "food-truck", "backflow", "water-quality", "pws", "sewer-credit", 
    "pos-form", "pos", "point-of-sale", "master-plan", "vr_form", 
    "agreement", "rental", "park-rental", "driveway", "pavilion"
]

NON_DOCUMENT_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.zip', '.docx', '.xlsx', '.css', '.js')


def get_pdf_from_wp_id(attachment_id, cache):
    """Asks the WP REST API for the direct media source URL using its attachment ID."""
    if attachment_id in cache:
        return cache[attachment_id]

    api_url = f"https://www.sheffieldlake.net/wp-json/wp/v2/media/{attachment_id}"
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            source_url = data.get("source_url")
            if source_url and ".pdf" in source_url.lower():
                cache[attachment_id] = source_url
                return source_url
    except Exception:
        pass

    cache[attachment_id] = None
    return None


def download_pdf(pdf_url, processed_pdf_urls):
    """Downloads the PDF to the local raw_pdfs folder."""
    parsed = urlparse(pdf_url)
    if "sheffieldlake.net" not in parsed.netloc:
        return False, "external"
        
    url_lower = pdf_url.lower()
    if any(term in url_lower for term in IGNORE_TERMS):
        return False, "ignored"

    if pdf_url in processed_pdf_urls:
        return False, "duplicate"

    processed_pdf_urls.add(pdf_url)

    filename = Path(parsed.path).name
    filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"

    local_path = DOWNLOAD_DIR / filename

    if local_path.exists():
        return False, "exists"

    try:
        r = requests.get(pdf_url, headers=HEADERS, timeout=20)
        r.raise_for_status()

        # Reject HTML response pages
        if len(r.content) < 100 or b"<!DOCTYPE" in r.content[:200] or b"<html" in r.content[:200].lower():
            return False, "not_a_pdf"

        print(f"  [+] DOWNLOADING: {filename}")
        with open(local_path, "wb") as f:
            f.write(r.content)
        return True, "downloaded"
    except Exception as e:
        print(f"  [!] Failed {pdf_url}: {e}")
        return False, "error"


def extract_pdfs_from_html(html_content, base_url):
    """Extracts direct PDF URLs and relative wp-content/uploads/ paths from HTML."""
    found_urls = set()

    soup = BeautifulSoup(html_content, "html.parser")
    for tag in soup.find_all(["a", "iframe", "embed", "object", "meta"]):
        for attr in ["href", "src", "data", "content"]:
            val = tag.get(attr)
            if not val:
                continue
            
            clean_val = val.replace('\\/', '/')
            full_url = urljoin(base_url, clean_val)
            full_lower = full_url.lower()

            if ".pdf" in full_lower or "/wp-content/uploads/" in full_lower:
                if not any(full_lower.endswith(ext) for ext in NON_DOCUMENT_EXTS):
                    found_urls.add(full_url)

    # Regex fallback for explicit PDF URLs
    matches = re.findall(r'(https?:\\?/\\?/[^\s\'"<>]+?\.pdf(?:\?[^\s\'"<>]*)?)', html_content, re.IGNORECASE)
    for m in matches:
        clean = m.replace('\\/', '/')
        found_urls.add(urljoin(base_url, clean))

    return found_urls


def scrape_all():
    downloaded_count = 0
    skipped_count = 0
    processed_pdf_urls = set()
    id_cache = {}
    visited_subpages = set()

    print(f"[+] Scraping {len(TARGET_PAGES)} yearly landing pages...\n")

    for idx, landing_url in enumerate(TARGET_PAGES, start=1):
        print(f"[{idx}/{len(TARGET_PAGES)}] Scanning: {landing_url}")
        try:
            r = requests.get(landing_url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                print(f"  [!] Failed to load page ({r.status_code})")
                continue
            html_content = r.text
        except Exception as e:
            print(f"  [!] Exception fetching {landing_url}: {e}")
            continue

        soup = BeautifulSoup(html_content, "html.parser")
        unresolved_subpages = set()

        # Step 1: Parse all anchor tags on the landing page
        for a in soup.find_all("a", href=True):
            href = urljoin(landing_url, a["href"]).split('#')[0]
            parsed_href = urlparse(href)

            if "sheffieldlake.net" not in parsed_href.netloc:
                continue

            # Case A: Direct .PDF link
            if href.lower().endswith(".pdf"):
                success, reason = download_pdf(href, processed_pdf_urls)
                if success:
                    downloaded_count += 1
                elif reason == "exists":
                    skipped_count += 1
                continue

            # Case B: Look for WordPress Attachment ID in rel or class attributes
            rel_attr = a.get("rel", [])
            rel_str = " ".join(rel_attr) if isinstance(rel_attr, list) else str(rel_attr)
            class_attr = a.get("class", [])
            class_str = " ".join(class_attr) if isinstance(class_attr, list) else str(class_attr)
            
            combined_attrs = f"{rel_str} {class_str}"
            att_match = re.search(r'wp-att-(\d+)', combined_attrs)

            if att_match:
                att_id = att_match.group(1)
                direct_pdf = get_pdf_from_wp_id(att_id, id_cache)
                if direct_pdf:
                    success, reason = download_pdf(direct_pdf, processed_pdf_urls)
                    if success:
                        downloaded_count += 1
                    elif reason == "exists":
                        skipped_count += 1
                    continue

            # Case C: Collect subpage URL for fallback HTML crawling
            if not href.lower().endswith(NON_DOCUMENT_EXTS):
                landing_path = parsed_href.path.rstrip('/')
                if landing_path and landing_path != urlparse(landing_url).path.rstrip('/'):
                    unresolved_subpages.add(href)

        # Step 2: Fallback HTML crawling for links that had no attachment ID
        for sub_url in unresolved_subpages:
            if sub_url in visited_subpages:
                continue

            visited_subpages.add(sub_url)
            try:
                sub_r = requests.get(sub_url, headers=HEADERS, timeout=10)
                if sub_r.status_code == 200:
                    sub_pdfs = extract_pdfs_from_html(sub_r.text, sub_url)
                    for pdf_url in sub_pdfs:
                        success, reason = download_pdf(pdf_url, processed_pdf_urls)
                        if success:
                            downloaded_count += 1
                        elif reason == "exists":
                            skipped_count += 1
            except Exception:
                pass

    print(f"\n==========================================")
    print(f"Full Site Sync Complete!")
    print(f"New Downloads: {downloaded_count} | Already Existing: {skipped_count}")


if __name__ == "__main__":
    scrape_all()