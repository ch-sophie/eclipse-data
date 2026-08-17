"""
Step 1 Raw ingestion of solar eclipse catalog data from eclipse.gsfc.nasa.gov.
This script: 
- fetches each catalog page
- finds all <pre> blocks and extracts their plain text (link text only, via BeautifulSoup's get_text, which strips the <a> tags but keeps the visible numbers/labels)
- Parses each data line with a regex tailored to the known column layout, tolerant of the optional trailing "path width" and "central duration" fields (only present for total/annular/hybrid eclipses with a defined path)
- Saves the parsed rows AS-IS (raw types, no further cleaning) into raw/<type>_<range>.csv
- Logs into raw/manifest.csv
"""
import os
import re
import csv
import time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

### CONFIG
load_dotenv()

RAW_DIR = os.path.join("data", "raw")
MANIFEST_PATH = os.path.join(RAW_DIR, "manifest.csv")

HEADERS = {
    "User-Agent": f"eclipse-data-project/0.1 (personal portfolio project; "
                  f"contact: {os.environ.get('CONTACT_EMAIL', 'unknown@example.com')})"
}

SOLAR_SOURCES = [
    {"label": "1901_2000", "url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE1901-2000.html"},
    {"label": "2001_2100", "url": "https://eclipse.gsfc.nasa.gov/SEcat5/SE2001-2100.html"},
]

SOLAR_COLUMNS = [
    "catalog_number", "year", "month", "day", "td_greatest_eclipse",
    "delta_t_s", "luna_num", "saros_num", "eclipse_type", "qle",
    "gamma", "magnitude", "lat", "long", "sun_alt",
    "path_width_km", "central_duration",
]

SOLAR_ROW_PATTERN = re.compile(
    r'^(\d+)\s+(-?\d+)\s+(\S+)\s+(\d+)\s+(\d{1,2}:\d{2}:\d{2})\s+(\d+)\s+(\d+)\s+(\d+)\s+'
    r'(\S+)\s+(\S+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+[NS])\s+(\d+[EW])\s+(\d+)'
    r'(?:\s+(\S+)\s+(\d+m\d+s))?\s*$'
)

### HELPERS FUNCTIONS
def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text

def parse_solar_catalog(html: str) -> list[list[str]]:
    """
    Extract data rows from every <pre> block on a solar eclipse catalog page
    Returns a list of field-lists (raw strings, unparsed/untyped)
    """
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for pre in soup.find_all("pre"):
        text = pre.get_text()
        for line in text.splitlines():
            match = SOLAR_ROW_PATTERN.match(line.strip())
            if match:
                rows.append(list(match.groups()))

    return rows

def append_manifest_row(row: dict) -> None:
    file_exists = os.path.isfile(MANIFEST_PATH)
    with open(MANIFEST_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def save_rows(rows: list[list[str]], columns: list[str], out_path: str) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

### MAIN
def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    for source in SOLAR_SOURCES:
        label = source["label"]
        url = source["url"]
        out_filename = f"solar_{label}.csv"
        out_path = os.path.join(RAW_DIR, out_filename)

        print(f"Fetching solar eclipses ({label}) from {url} ...")

        try:
            html = fetch_html(url)
            rows = parse_solar_catalog(html)

            if not rows:
                raise RuntimeError(
                    "0 rows matched - the page structure may differ from what was inspected."
                )
            save_rows(rows, SOLAR_COLUMNS, out_path)

            append_manifest_row({
                "eclipse_type": "solar",
                "date_range_label": label,
                "source_url": url,
                "rows_extracted": len(rows),
                "output_file": out_filename,
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "ok",
            })
            print(f"-> saved {len(rows)} rows to {out_path}")

        except Exception as exc:
            append_manifest_row({
                "eclipse_type": "solar",
                "date_range_label": label,
                "source_url": url,
                "rows_extracted": 0,
                "output_file": "",
                "pulled_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": f"error: {exc}",
            })
            print(f"-> FAILED: {exc}")

        time.sleep(2) #polite delay between requests

    print(f"\nDone. Manifest written to {MANIFEST_PATH}")

if __name__ == "__main__":
    main()