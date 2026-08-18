"""
Step 2 Cleaning & standardization, matching step 1 actual output columns
- No date_raw parsing needed: year/month/day already arrive as separate raw columns straight from the source, so we just type-convert them
- eclipse_type in the raw data includes compound codes (ex "An", "A-", "H3", "Pb") beyond the single-letter base types documented in NASA summary stats
"""
import os
import glob
import pandas as pd

RAW_DIR = os.path.join("data", "raw")
CLEAN_DIR = os.path.join("data", "clean")

BASE_TYPE_MAP = {
    "P": "Partial",
    "A": "Annular",
    "T": "Total",
    "H": "Hybrid",
}

def parse_coordinate(value: str):
    """
    Parse a coordinate string like '11S' or '131E' into a signed float
    Returns None for missing/blank values
    """
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "-", "--", "NAN"}:
        return None

    direction = text[-1].upper()
    number_part = text[:-1]
    if direction not in ("N", "S", "E", "W") or not number_part:
        return None

    try:
        magnitude = float(number_part)
    except ValueError:
        return None

    if direction in ("S", "W"):
        magnitude *= -1
    return magnitude

def parse_duration_to_seconds(value: str):
    """Parse a duration string like '04m57s' into total seconds int"""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if "m" not in text or "s" not in text:
        return None
    try:
        minutes_part, seconds_part = text.split("m")
        seconds_part = seconds_part.replace("s", "")
        return int(minutes_part) * 60 + int(seconds_part)
    except ValueError:
        return None

def split_eclipse_type(raw_type: str):
    """
    Split a raw type code (ex 'An', 'H3', 'T', '-') into a confidently known base type and an untouched suffix for later lookup
    """
    text = str(raw_type).strip()
    if not text:
        return "UNKNOWN (empty)", ""

    base_letter = text[0].upper()
    base_type = BASE_TYPE_MAP.get(base_letter, f"UNKNOWN ({text})")
    suffix = text[1:]  #everything after the first letter, untouched
    return base_type, suffix

def clean_solar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # --- Date fields: already separate, just type-convert ---
    df["astronomical_year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["day"] = pd.to_numeric(df["day"], errors="coerce").astype("Int64")

    # --- Eclipse type: split into confidently-known base + raw suffix ---
    split_result = df["eclipse_type"].map(split_eclipse_type)
    df["eclipse_type_clean"] = split_result.map(lambda t: t[0])
    df["eclipse_type_suffix_raw"] = split_result.map(lambda t: t[1])

    n_unknown = df["eclipse_type_clean"].astype(str).str.startswith("UNKNOWN").sum()
    if n_unknown:
        print(f"! {n_unknown} rows have an unrecognized base eclipse type letter - "
              f"inspect eclipse_type_clean values starting with 'UNKNOWN'.")

    # --- Numeric fields ---
    for col in ("delta_t_s", "luna_num", "saros_num", "sun_alt", "path_width_km"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ("gamma", "magnitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # --- Coordinates ---
    df["latitude"] = df["lat"].map(parse_coordinate)
    df["longitude"] = df["long"].map(parse_coordinate)

    # --- Duration ---
    df["central_duration_seconds"] = df["central_duration"].map(parse_duration_to_seconds)
    df["eclipse_category"] = "solar"

    return df

def main():
    os.makedirs(CLEAN_DIR, exist_ok=True)

    pattern = os.path.join(RAW_DIR, "solar_*.csv")
    raw_files = sorted(glob.glob(pattern))

    if not raw_files:
        print(f"No raw files found for pattern {pattern} - run step1 first.")
        return

    print(f"Cleaning {len(raw_files)} raw solar file(s)...")

    cleaned_frames = []
    for path in raw_files:
        raw_df = pd.read_csv(path, dtype=str)  #read as str first; type-convert ourselves
        cleaned_df = clean_solar_dataframe(raw_df)
        cleaned_frames.append(cleaned_df)
        print(f"- {path}: {len(raw_df)} rows -> cleaned")

    combined = pd.concat(cleaned_frames, ignore_index=True)

    n_bad_years = combined["astronomical_year"].isna().sum()
    if n_bad_years:
        print(f"! {n_bad_years} rows have an unparsed year - inspect before proceeding.")

    n_missing_coords = combined["latitude"].isna().sum()
    if n_missing_coords:
        print(f"! {n_missing_coords} rows have no parsed latitude "
              f"(expected for many partial eclipses, which lack a defined path point - "
              f"confirm this count roughly matches partial-eclipse count).")

    out_path = os.path.join(CLEAN_DIR, "solar_eclipses_clean.csv")
    combined.to_csv(out_path, index=False)
    print(f"\n  -> saved {len(combined)} total rows to {out_path}")

if __name__ == "__main__":
    main()