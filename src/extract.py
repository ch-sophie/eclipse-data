"""
Step 1 — Raw ingestion of solar & lunar eclipse catalog data
What this script does:
- Fetches a set of catalog pages (one per century/date-range, per eclipse type)
- Parses the HTML table on each page into a pandas DataFrame
- Saves each DataFrame as is (no cleaning) into raw/<type>_<range>.csv
- Logs what was pulled into raw/manifest.csv

Requirements:
    pip install requests beautifulsoup4 pandas lxml
"""
import os
import time
import csv
from datetime import datetime, timezone
import requests
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os

### CONFIG
RAW_DIR = "raw"
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.csv")

load_dotenv()

HEADERS = {
    "User-Agent": f"eclipse-data-project/0.1 (personal portfolio project; contact: {os.environ['CONTACT_EMAIL']})"
}

SOURCES = [
    {
        "type": "solar",
        "label": "2001_2100",
        "url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html",
    },
    {
        "type": "solar",
        "label": "1901_2000",
        "url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html",
    },
    {
        "type": "lunar",
        "label": "2001_2100",
        "url": "https://eclipse.gsfc.nasa.gov/LEcat5/LE2001-2100.html",
    },
    {
        "type": "lunar",
        "label": "1901_2000",
        "url": "https://eclipse.gsfc.nasa.gov/LEcat5/LE1901-2000.html",
    },
]

### HELPERS FUNCTIONS
def fetch_html(url: str) -> str:
    """Download raw HTML for a single catalog page."""
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text

def extract_table(html: str) -> pd.DataFrame:
    """
    Try the easy path first (pandas.read_html) then fall back to manual beautifulsoup parsing if the page's table is too irregular for pandas to detect cleanly (merged cells, footnote markers, etc)
    """
    try:
        tables = pd.read_html(html)
        if tables:
            return max(tables, key=lambda df: df.shape[0])
    except ValueError:
        pass  #pandas found no parsable tables - fall back below

    #MANUAL FALLBACK 
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("No <table> found on page — inspect HTML manually")

    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)

    if not rows:
        raise RuntimeError("Table found but no rows extracted — inspect HTML manually")

    header, *data_rows = rows
    return pd.DataFrame(data_rows, columns=header)

def append_manifest_row(row: dict) -> None:
    """Append one entry to the manifest log, creating the file with a header if needed"""
    file_exists = os.path.isfile(MANIFEST_PATH)
    with open(MANIFEST_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

### MAIN 
def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    for source in SOURCES:
        eclipse_type = source["type"]
        label = source["label"]
        url = source["url"]
        out_filename = f"{eclipse_type}_{label}.csv"
        out_path = os.path.join(RAW_DIR, out_filename)

        print(f"Fetching {eclipse_type} eclipses ({label}) from {url} ...")

        try:
            html = fetch_html(url)
            df = extract_table(html)
            df.to_csv(out_path, index=False)

            append_manifest_row({
                "eclipse_type": eclipse_type,
                "date_range_label": label,
                "source_url": url,
                "rows_extracted": len(df),
                "output_file": out_filename,
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "ok",
            })
            print(f"  -> saved {len(df)} rows to {out_path}")

        except Exception as exc:
            # Log failures too, rather than silently skipping
            append_manifest_row({
                "eclipse_type": eclipse_type,
                "date_range_label": label,
                "source_url": url,
                "rows_extracted": 0,
                "output_file": "",
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": f"error: {exc}",
            })
            print(f"  -> FAILED: {exc}")

        time.sleep(2) 

    print(f"\nDone. Manifest written to {MANIFEST_PATH}")

if __name__ == "__main__":
    main()