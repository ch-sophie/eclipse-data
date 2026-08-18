"""
Step 4 Enrich solar eclipse data with country/continent, via offline reverse geocoding of the 'greatest eclipse' lat/long point

IMPORTANT CAVEAT (read before trusting the output):
NASA's lat/long columns mark the point of GREATEST eclipse - a single point, not the full path. Many eclipses greatest-eclipse point fall over open ocean (this is common). Reverse geocoding always returns the NEAREST populated place regardless of how far away it is, so a point in the middle of the Pacific will still get matched to some island or coastline, which can be misleading if taken at face value.

To handle this, this script also computes the great-circle distance from each eclipse point to its matched nearest place, and adds an `is_likely_ocean` flag (default threshold: 300 km).
+ greatest-eclipse point is only ONE point in an eclipse's path.
A total/annular eclipse's shadow path crosses many countries, not just the one nearest its single greatest-eclipse point. This enrichment tells you "where was the eclipse at its peak" not "every country it was visible from"
"""
import os
import sqlite3
import math
import pandas as pd
import reverse_geocoder as rg
import pycountry
import pycountry_convert as pc

PROCESSED_DIR = os.path.join("data", "db")
DB_PATH = os.path.join(PROCESSED_DIR, "eclipses.db")
TABLE_NAME = "solar_eclipses"

OCEAN_DISTANCE_THRESHOLD_KM = 300

CONTINENT_CODE_TO_NAME = {
    "AF": "Africa",
    "AS": "Asia",
    "EU": "Europe",
    "NA": "North America",
    "SA": "South America",
    "OC": "Oceania",
    "AN": "Antarctica",
}

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/long points in km"""
    r = 6371.0  #Earth radius, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))

def country_code_to_names(alpha2: str):
    """Return (country_name, continent_name) for an ISO alpha-2 code, or (None, None)"""
    if not alpha2:
        return None, None
    try:
        country = pycountry.countries.get(alpha_2=alpha2)
        country_name = country.name if country else None
    except Exception:
        country_name = None

    try:
        continent_code = pc.country_alpha2_to_continent_code(alpha2)
        continent_name = CONTINENT_CODE_TO_NAME.get(continent_code)
    except Exception:
        continent_name = None

    return country_name, continent_name

def enrich_with_geography(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    has_coords = df["latitude"].notna() & df["longitude"].notna()
    coords = list(zip(df.loc[has_coords, "latitude"], df.loc[has_coords, "longitude"]))

    print(f"Reverse geocoding {len(coords)} rows with coordinates "
          f"({(~has_coords).sum()} rows have no coordinates and will be skipped)...")

    results = rg.search(coords, mode=1) if coords else []

    nearest_place_name = []
    nearest_lat = []
    nearest_lon = []
    country_code = []

    for r in results:
        nearest_place_name.append(r.get("name"))
        nearest_lat.append(float(r.get("lat")))
        nearest_lon.append(float(r.get("lon")))
        country_code.append(r.get("cc"))

    enriched = pd.DataFrame({
        "nearest_place_name": nearest_place_name,
        "nearest_place_lat": nearest_lat,
        "nearest_place_lon": nearest_lon,
        "country_code": country_code,
    }, index=df.loc[has_coords].index)

    df = df.join(enriched)

    # Distance from the eclipse greatest-eclipse point to the matched nearest place - this is what flags "probably open ocean"
    def compute_distance(row):
        if pd.isna(row.get("nearest_place_lat")):
            return None
        return haversine_km(
            row["latitude"], row["longitude"],
            row["nearest_place_lat"], row["nearest_place_lon"],
        )

    df["distance_to_nearest_place_km"] = df.apply(compute_distance, axis=1)
    df["is_likely_ocean"] = df["distance_to_nearest_place_km"] > OCEAN_DISTANCE_THRESHOLD_KM

    # Country/continent names from the ISO code
    name_lookup = df["country_code"].map(
        lambda cc: country_code_to_names(cc) if pd.notna(cc) else (None, None)
    )
    df["country_name"] = name_lookup.map(lambda t: t[0])
    df["continent"] = name_lookup.map(lambda t: t[1])

    # For likely-ocean, null out the country/continent claim rather than assert a misleading answer, but keep the nearest-place info for reference (ex "nearest to Fiji" is still informative context)
    ocean_mask = df["is_likely_ocean"] == True  #noqa: E712 (explicit for clarity with NaN)
    df.loc[ocean_mask, ["country_name", "continent"]] = None

    return df

def rebuild_table_with_geography(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

def main():
    if not os.path.isfile(DB_PATH):
        print(f"No database found at {DB_PATH} - run step 3 first.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM {TABLE_NAME}", conn)
        print(f"Loaded {len(df)} rows from '{TABLE_NAME}'")

        enriched = enrich_with_geography(df)
        rebuild_table_with_geography(conn, enriched)
        conn.commit()

        n_with_country = enriched["country_name"].notna().sum()
        n_ocean = enriched["is_likely_ocean"].sum()
        n_no_coords = enriched["latitude"].isna().sum()

        print(f"\nDone. Table '{TABLE_NAME}' rebuilt with geography columns.")
        print(f"Rows with a resolved country: {n_with_country}")
        print(f"Rows flagged as likely-ocean (>{OCEAN_DISTANCE_THRESHOLD_KM}km "
              f"from nearest place): {n_ocean}")
        print(f"Rows with no coordinates at all (typically partial eclipses "
              f"with no defined path point): {n_no_coords}")

        cursor = conn.execute(
            f"SELECT continent, COUNT(*) FROM {TABLE_NAME} "
            f"WHERE continent IS NOT NULL GROUP BY continent ORDER BY COUNT(*) DESC"
        )
        print("\nBreakdown by continent (excluding ocean/no-coordinate rows):")
        for continent, count in cursor.fetchall():
            print(f"{continent}: {count}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()