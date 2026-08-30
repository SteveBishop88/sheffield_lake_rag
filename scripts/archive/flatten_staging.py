# 8/23/26 this file is no longer used

# flattends the directory structure so all pdfs are in on directory.
# the scraper.py file created subdirectories, which is fine but I wanted
# to have all of the pdf files in one spot.



import os
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW_BY_YEAR_DIR = os.path.join(PROJECT_ROOT, "data", "raw_pdfs")
STAGING_DIR = os.path.join(PROJECT_ROOT, "data", "staging_all_pdfs")

os.makedirs(STAGING_DIR, exist_ok=True)

copied_count = 0
for root, _, files in os.walk(RAW_BY_YEAR_DIR):
    for filename in files:
        if filename.lower().endswith(".pdf"):
            year_folder = os.path.basename(root)
            # Prefix year to maintain uniqueness and year metadata
            staged_filename = f"{year_folder}_{filename}"
            src_path = os.path.join(root, filename)
            dst_path = os.path.join(STAGING_DIR, staged_filename)

            shutil.copy2(src_path, dst_path)
            copied_count += 1

print(f"[✓] Successfully staged {copied_count} PDFs into: {STAGING_DIR}")