# 8/23/26 this file is no longer used


# takes the pdfs in the staging_all_pdfs directory and parses them into
# categories.

import os
import re
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

SOURCE_DIR = PROJECT_ROOT / "data" / "staging_all_pdfs"
DEST_DIR = PROJECT_ROOT / "data" / "categorized_pdfs"

# Category detection rules and clean prefix labels
CATEGORY_MAP = [
    # Expanded truncated matchers
    (r"council|ouncil|^coun\.pdf$|^c\.pdf$", "Council"),
    (r"worksession|work_session", "Work_Session"),
    (r"roads_drains|ads_drains", "Roads_Drains"),
    (r"buildings_lands", "Buildings_Lands"),
    (r"safety|ty_|^safe\.pdf$", "Safety"),
    # PB catch-all for PB04152013 style files
    (r"park_board|^pb\d{6,8}", "Park_Board"),
    (r"planning", "Planning_Commission"),
    (r"zba|zoning", "Zoning_Board"),
    (r"ordinance", "Ordinance"),
    (r"finance", "Finance"),
    (r"public_hearing", "Public_Hearing"),
    (r"records_commission", "Records_Commission"),
    (r"appropriations", "Appropriations"),
    (r"special_meeting|special", "Special_Meeting"),
    (r"sewer", "Sewer"),
    # New Categories Added
    (r"demolition_board", "Demolition_Board"),
    (r"civic_center|joyce_hanks", "Civic_Center"),
]


def standardize_and_copy():
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(f"Source directory does not exist: {SOURCE_DIR}")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    for filepath in SOURCE_DIR.iterdir():
        if not filepath.is_file() or filepath.suffix.lower() != ".pdf":
            continue

        filename = filepath.name

        # 1. Clean merged format artifacts (e.g., 'mod1docx.pdf' -> '.pdf')
        cleaned_name = re.sub(
            r"mod\d+docx\.pdf$", ".pdf", filename, flags=re.IGNORECASE
        )

        # 2. Fix known truncated or broken prefixes
        cleaned_name = re.sub(
            r"^(\d{4})_ads_drains", r"\1_Roads_Drains", cleaned_name
        )
        cleaned_name = re.sub(
            r"^(\d{4})_ouncil", r"\1_Council", cleaned_name
        )
        cleaned_name = re.sub(
            r"^(\d{4})_ty_", r"\1_Safety_", cleaned_name
        )

        # 3. Standardize formatting (spaces to underscores)
        cleaned_name = re.sub(r"\s+", "_", cleaned_name)

        # 4. Detect category keyword
        category_tag = "Uncategorized"
        for pattern, tag in CATEGORY_MAP:
            if re.search(pattern, cleaned_name, re.IGNORECASE):
                category_tag = tag
                break

        # 5. Ensure category tag is explicitly embedded after the year prefix
        year_match = re.match(r"^(\d{4})_(.*)", cleaned_name)
        if year_match:
            year, rest = year_match.groups()
            # If the category isn't already in the filename, prepend it after the year
            if category_tag.lower() not in rest.lower():
                cleaned_name = f"{year}_{category_tag}_{rest}"
        elif category_tag.lower() not in cleaned_name.lower():
            cleaned_name = f"{category_tag}_{cleaned_name}"

        # Clean up any potential double underscores from regex replacement
        cleaned_name = re.sub(r"__+", "_", cleaned_name)

        target_path = DEST_DIR / cleaned_name

        # Non-destructive copy (leaves staging directory intact)
        os.chmod(filepath, 0o644)
        shutil.copy2(filepath, target_path)
        print(f"Copied: {filename} -> categorized_pdfs/{cleaned_name}")


if __name__ == "__main__":
    standardize_and_copy()