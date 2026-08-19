# Solar Eclipse Explorer

A data engineering project that scrapes, cleans and stores NASA's historical solar eclipse catalog, then presents it through an interactive Streamlit dashboard, with maps, timelines and Saros cycle exploration.

The app is deployed here: *[Solar Eclipse Explorer](https://eclipse-data.onrender.com)*

### Data source & attribution
Data comes from NASA/GSFC's Five Millennium Catalog of Solar Eclipses (-1999 to +3000), compiled by Fred Espenak and Jean Meeus, hosted at [eclipse.gsfc.nasa.gov](https://eclipse.gsfc.nasa.gov/eclipse.html)

> Eclipse Predictions by Fred Espenak and Jean Meeus (NASA's GSFC)

Permission is freely granted to reproduce this data when accompanied by the above acknowledgment, which is why it's reproduced here.

Currently covers **solar eclipses from 1901–2100** (two catalog pages). Lunar eclipses and full eclipse-path data are documented as future extensions below.

### Architecture
This dataset is static, historical, and small (a few hundred rows). The project uses a simple **raw → clean → processed** convention:
- **raw/** - scraped data, untouched, exactly as pulled from the source
- **clean/** - typed, standardized, deduplicated
- **db/** - a queryable SQLite database, ready for the app to read

### Pipeline
| Step | Script | What it does |
|---|---|---|
| 1 | `extract.py` | Scrapes NASA's `<pre>`-formatted catalog pages, parses fixed-width rows via regex, saves raw CSVs + a manifest log |
| 2 | `clean.py` | Types and standardizes raw data: parses eclipse type codes, coordinates, durations; flags unparseable rows instead of dropping them silently |
| 3 | `load_db.py` | Loads cleaned data into `data/db/eclipses.db` with an explicit schema |
| 4 | `add_geopoint.py` | Enriches each row with nearest country/continent via offline reverse geocoding, and flags points likely over open ocean |

### A few real data-quality issues hit along the way
- NASA's catalog data lives in `<pre>` blocks, not HTML `<table>` tags, required a custom regex parser rather than `pandas.read_html()`
- ΔT and Luna Num are **negative** for dates before their respective reference epochs (early 1900s) - only allowed positive integers here, silently dropping most of the 1901–2000 catalog until caught by comparing row counts across files
- Eclipse type codes include compound suffixes (`An`, `H3`, `Pb`, etc.) beyond the four base types - rather than guess at undocumented suffix meanings, the base type (confidently known) and raw suffix (kept as-is for later lookup) are stored separately
- The greatest-eclipse point is a single coordinate, often over open ocean: reverse geocoding always returns *something* nearby regardless of distance

### Database schema (`solar_eclipses` table)
| Column | Type | Notes |
|---|---|---|
| `catalog_number` | TEXT | NASA's own catalog ID |
| `astronomical_year` | INTEGER | 0 = 1 BCE, negative = further BCE |
| `month`, `day` | TEXT / INTEGER | |
| `eclipse_type_clean` | TEXT | Partial / Annular / Total / Hybrid |
| `eclipse_type_suffix_raw` | TEXT | Undocumented sub-classification code, kept raw |
| `saros_num` | INTEGER | Saros series this eclipse belongs to |
| `magnitude`, `gamma` | REAL | |
| `latitude`, `longitude` | REAL | Point of greatest eclipse |
| `path_width_km`, `central_duration_seconds` | REAL | Null for partial eclipses |
| `country_name`, `continent` | TEXT | From Step 4; null if over open ocean |
| `is_likely_ocean` | BOOLEAN | From Step 4 |

### Streamlit app
```bash
pip install -r requirements.txt
streamlit run app/app.py
```

- **Map** - greatest-eclipse locations, colored by type, with a toggle to
  visually highlight total eclipses
- **Timeline** - eclipses per decade/century and by continent
- **Saros Explorer** - pick a Saros series, see how its path drifts across
  centuries
- **Data Table** - filtered results, downloadable as CSV
- **Eclipse Path** - project info and NASA's own eclipse atlas reference images
  (2001–2100, in 20-year periods)

#### Known limitations / future work
- **Lunar eclipses** not yet implemented (different catalog page layout, needs its own parser)
- **Only the greatest-eclipse point is shown**, not the full shadow path. NASA publishes per-eclipse path tables (northern/southern limit + center line) at a separate URL per eclipse (a planned Step 1b, not yet built) requiring one HTTP request per central eclipse rather than per century
- **Country/continent are approximate**, based on nearest populated place to a single point - not a full path-crossing analysis
- Currently covers 1901–2100; earlier/later centuries follow the same URL pattern and could be added by extending `SOLAR_SOURCES`

#### Tools used
Python (`requests`, `BeautifulSoup`, `pandas`), SQLite, offline reverse geocoding (`reverse_geocoder`, `pycountry`, `pycountry-convert`), Streamlit, `pydeck`, `plotly`. Deployed on Render.