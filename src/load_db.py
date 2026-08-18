"""
Step 3 - Load cleaned data into SQLite db
Reads data/clean/ and loads it into a single table in a SQLite db file under data/processed/
This is a typed, queryable store that streamlit app (or any SQL client) can read directly 
"""
import os
import sqlite3
import pandas as pd

CLEAN_DIR = os.path.join("data", "clean")
PROCESSED_DIR = os.path.join("data", "db")

CLEAN_CSV_PATH = os.path.join(CLEAN_DIR, "solar_eclipses_clean.csv")
DB_PATH = os.path.join(PROCESSED_DIR, "eclipses.db")

TABLE_NAME = "solar_eclipses"

SCHEMA = {
    "catalog_number": "TEXT PRIMARY KEY",
    "astronomical_year": "INTEGER",
    "month": "TEXT",
    "day": "INTEGER",
    "td_greatest_eclipse": "TEXT",
    "delta_t_s": "REAL",
    "luna_num": "INTEGER",
    "saros_num": "INTEGER",
    "eclipse_type_clean": "TEXT",
    "eclipse_type_suffix_raw": "TEXT",
    "qle": "TEXT",
    "gamma": "REAL",
    "magnitude": "REAL",
    "latitude": "REAL",
    "longitude": "REAL",
    "sun_alt": "REAL",
    "path_width_km": "REAL",
    "central_duration_seconds": "REAL",
    "eclipse_category": "TEXT",
}

def create_table(conn: sqlite3.Connection) -> None:
    columns_sql = ",\n".join(f"{col} {sqltype}" for col, sqltype in SCHEMA.items())
    conn.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
    conn.execute(f"CREATE TABLE {TABLE_NAME} (\n{columns_sql}\n)")

def load_data(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    # Keep only the columns defined in schema in that order - anything extra in the CSV (like leftover raw columns from step 2) is dropped
    missing = [col for col in SCHEMA if col not in df.columns]
    if missing:
        raise RuntimeError(
            f"Clean CSV is missing expected column(s): {missing}. "
            f"Check step 2 ran successfully and produced these columns."
        )

    df_to_load = df[list(SCHEMA.keys())].copy()

    df_to_load = df_to_load.astype(object).where(pd.notnull(df_to_load), None)

    df_to_load.to_sql(TABLE_NAME, conn, if_exists="append", index=False)
    return len(df_to_load)

def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    if not os.path.isfile(CLEAN_CSV_PATH):
        print(f"No clean data found at {CLEAN_CSV_PATH} - run step 2 first.")
        return

    df = pd.read_csv(CLEAN_CSV_PATH)
    print(f"Loaded {len(df)} rows from {CLEAN_CSV_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        create_table(conn)
        n_loaded = load_data(conn, df)
        conn.commit()
        print(f"Loaded {n_loaded} rows into '{TABLE_NAME}' table in {DB_PATH}")

        #Quick sanity check: row count and a breakdown by eclipse type, read back from db itself rather than trusted from memory
        cursor = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
        print(f"Verified row count in DB: {cursor.fetchone()[0]}")

        cursor = conn.execute(
            f"SELECT eclipse_type_clean, COUNT(*) FROM {TABLE_NAME} "
            f"GROUP BY eclipse_type_clean ORDER BY COUNT(*) DESC"
        )
        print("Breakdown by eclipse type:")
        for eclipse_type, count in cursor.fetchall():
            print(f"  {eclipse_type}: {count}")

    finally:
        conn.close()

if __name__ == "__main__":
    main()