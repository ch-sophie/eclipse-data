"""
Streamlit app for exploring the solar eclipse dataset
Reads directly from eclipses.db
"""
import os
import sqlite3
import pandas as pd
import streamlit as st
import pydeck as pdk
import plotly.express as px

DB_PATH = os.path.join("data", "db", "eclipses.db")
TABLE_NAME = "solar_eclipses"

TYPE_COLORS = {
    "Total": "#d62728",      # red - the rare, dramatic ones
    "Annular": "#ff7f0e",    # orange
    "Hybrid": "#9467bd",     # purple
    "Partial": "#7f7f7f",    # gray
}

MONTH_NUM = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

def build_nasa_link(row) -> str | None:
    """
    Build a link to NASA per-eclipse page:
    https://eclipse.gsfc.nasa.gov/SEsearch/SEsearchmap.php?Ecl=20260812
    Returns None for BCE dates (astronomical_year < 1), which this NASA tool doesn't support via this URL pattern
    """
    year = row.get("astronomical_year")
    month = row.get("month")
    day = row.get("day")
    if pd.isna(year) or year < 1 or pd.isna(day) or month not in MONTH_NUM:
        return None
    return (
        f"https://eclipse.gsfc.nasa.gov/SEsearch/SEsearchmap.php"
        f"?Ecl={int(year):04d}{MONTH_NUM[month]}{int(day):02d}"
    )

def format_duration(seconds) -> str:
    if pd.isna(seconds):
        return "-"
    seconds = int(seconds)
    return f"{seconds // 60:02d}m{seconds % 60:02d}s"

### DATA LOADING
@st.cache_data
def load_data() -> pd.DataFrame:
    if not os.path.isfile(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql(f"SELECT * FROM {TABLE_NAME}", conn)
    finally:
        conn.close()
    return df

def has_geography(df: pd.DataFrame) -> bool:
    """Step 4 (geography enrichment) is optional - check if it's been run."""
    return "continent" in df.columns

### APP
st.set_page_config(page_title="Solar Eclipse Explorer", layout="wide")
st.title("☀️ Solar Eclipse Explorer")
st.caption("Eclipse Predictions by Fred Espenak (NASA's GSFC) — Five Millennium Catalog of Solar Eclipses")

df = load_data()

if df.empty:
    st.error(
        f"No data found at `{DB_PATH}`. Run step1-step4 "
    )
    st.stop()

geography_available = has_geography(df)

### SIDEBAR FILTERS
st.sidebar.header("Filters")

year_min = int(df["astronomical_year"].min())
year_max = int(df["astronomical_year"].max())
year_range = st.sidebar.slider(
    "Year range (astronomical numbering)",
    min_value=year_min, max_value=year_max,
    value=(year_min, year_max),
)

all_types = sorted(df["eclipse_type_clean"].dropna().unique())
selected_types = st.sidebar.multiselect(
    "Eclipse type", options=all_types, default=all_types,
)

highlight_totals = st.sidebar.checkbox("Highlight total eclipses", value=True)
totals_only = st.sidebar.checkbox("Show only total eclipses", value=False)

if geography_available:
    hide_ocean = st.sidebar.checkbox(
        "Hide eclipses flagged as over open ocean",
        value=False,
        help="Based on distance from the greatest-eclipse point to the nearest "
             "populated place. Many eclipses genuinely occur over open ocean, "
             "so this is off by default.",
    )
else:
    hide_ocean = False
    st.sidebar.info("Run step4 to add geo-points filters.")

### APPLY FILTERS
filtered = df[
    (df["astronomical_year"] >= year_range[0])
    & (df["astronomical_year"] <= year_range[1])
    & (df["eclipse_type_clean"].isin(selected_types))
].copy()

if totals_only:
    filtered = filtered[filtered["eclipse_type_clean"] == "Total"]

if hide_ocean and "is_likely_ocean" in filtered.columns:
    filtered = filtered[filtered["is_likely_ocean"] != True]  # noqa: E712

st.sidebar.markdown(f"**{len(filtered)}** eclipses match your filters")

### TOP-LEVEL STATS
col1, col2, col3, col4 = st.columns(4)
col1.metric("Eclipses shown", len(filtered))
col2.metric("Total eclipses", int((filtered["eclipse_type_clean"] == "Total").sum()))
col3.metric("Annular", int((filtered["eclipse_type_clean"] == "Annular").sum()))
col4.metric("Hybrid", int((filtered["eclipse_type_clean"] == "Hybrid").sum()))

### TABS
tab_map, tab_timeline, tab_saros, tab_table, tab_about = st.tabs(
    ["🗺️ Map", "📈 Timeline", "🔄 Saros Explorer", "📋 Data Table", "📖 Eclipse path"]
)

### MAP TAB
with tab_map:
    st.subheader("Greatest-eclipse locations")
    st.caption(
        "Each point marks the location of greatest eclipse (the single point "
        "where the Moon's shadow axis passed closest to Earth's center) - "
        "not the full path of visibility."
    )
    map_df = filtered.dropna(subset=["latitude", "longitude"]).copy()

    if map_df.empty:
        st.info("No eclipses with coordinates match the current filters "
                 "(many partial eclipses have no defined greatest-eclipse point).")
    else:
        def marker_color(eclipse_type: str, is_total_row: bool):
            if highlight_totals and eclipse_type == "Total":
                return [214, 39, 40, 220]  # bright red, high opacity
            base = {
                "Total": [214, 39, 40],
                "Annular": [255, 127, 14],
                "Hybrid": [148, 103, 189],
                "Partial": [127, 127, 127],
            }.get(eclipse_type, [100, 100, 100])
            opacity = 200 if not highlight_totals else 90  # dim non-totals when highlighting
            return base + [opacity]

        map_df["color"] = map_df["eclipse_type_clean"].apply(
            lambda t: marker_color(t, t == "Total")
        )
        map_df["radius"] = map_df["eclipse_type_clean"].apply(
            lambda t: 60000 if (highlight_totals and t == "Total") else 30000
        )

        tooltip_fields = ["catalog_number", "astronomical_year", "month", "day",
                           "eclipse_type_clean", "magnitude"]
        if geography_available:
            tooltip_fields += ["country_name", "continent", "is_likely_ocean"]

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position=["longitude", "latitude"],
            get_fill_color="color",
            get_radius="radius",
            pickable=True,
        )
        view_state = pdk.ViewState(latitude=10, longitude=0, zoom=1)
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            tooltip={"text": "Eclipse #{catalog_number}\n{astronomical_year} {month} {day}\n"
                              "Type: {eclipse_type_clean} | Mag: {magnitude}"},
        ))

        legend_cols = st.columns(len(TYPE_COLORS))
        for col, (etype, color) in zip(legend_cols, TYPE_COLORS.items()):
            col.markdown(f"<span style='color:{color}'>●</span> {etype}", unsafe_allow_html=True)

### TIMELINE TAB
with tab_timeline:
    st.subheader("Eclipses over time")

    bucket_choice = st.radio("Group by", ["Decade", "Century"], horizontal=True)
    bucket_size = 10 if bucket_choice == "Decade" else 100

    timeline_df = filtered.copy()
    timeline_df["bucket"] = (timeline_df["astronomical_year"] // bucket_size) * bucket_size

    counts = (
        timeline_df.groupby(["bucket", "eclipse_type_clean"])
        .size()
        .reset_index(name="count")
    )

    fig = px.bar(
        counts, x="bucket", y="count", color="eclipse_type_clean",
        color_discrete_map=TYPE_COLORS,
        labels={"bucket": bucket_choice, "count": "Number of eclipses",
                "eclipse_type_clean": "Type"},
        title=f"Solar eclipses per {bucket_choice.lower()}",
    )
    st.plotly_chart(fig, use_container_width=True)

    if geography_available:
        st.subheader("By continent")
        continent_counts = (
            filtered.dropna(subset=["continent"])
            .groupby("continent").size().reset_index(name="count")
            .sort_values("count", ascending=False)
        )
        if continent_counts.empty:
            st.info("No eclipses in the current filter have a resolved continent "
                     "(ocean-only selection).")
        else:
            fig2 = px.bar(continent_counts, x="continent", y="count",
                          title="Eclipses with greatest-eclipse point by continent "
                                "(excludes ocean/no-coordinate rows)")
            st.plotly_chart(fig2, use_container_width=True)

### SAROS EXPLORER TAB
with tab_saros:
    st.subheader("Saros cycle explorer")
    st.caption(
        "Each Saros series is a family of eclipses recurring roughly every 18 years. Eclipses in the same series follow a similar pattern (e.g. a partial series slowly becoming total, or an annular series drifting north-to-south) as their geometry evolves over centuries."
    )
    saros_options = sorted(df["saros_num"].dropna().unique().astype(int))
    selected_saros = st.selectbox("Choose a Saros series", saros_options)

    saros_df = df[df["saros_num"] == selected_saros].sort_values("astronomical_year")

    if saros_df.empty:
        st.info("No eclipses found for this Saros series in the current data.")
    else:
        st.write(
            f"Saros {selected_saros}: **{len(saros_df)} eclipses** in this dataset, "
            f"from **{int(saros_df['astronomical_year'].min())}** to "
            f"**{int(saros_df['astronomical_year'].max())}**."
        )

        st.dataframe(
            saros_df[["catalog_number", "astronomical_year", "month", "day",
                      "eclipse_type_clean", "eclipse_type_suffix_raw", "magnitude",
                      "latitude", "longitude"]],
            use_container_width=True,
            hide_index=True,
        )

        saros_map_df = saros_df.dropna(subset=["latitude", "longitude"])
        if not saros_map_df.empty:
            path_layer = pdk.Layer(
                "ScatterplotLayer",
                data=saros_map_df,
                get_position=["longitude", "latitude"],
                get_fill_color=[148, 103, 189, 180],
                get_radius=50000,
                pickable=True,
            )
            st.pydeck_chart(pdk.Deck(
                layers=[path_layer],
                initial_view_state=pdk.ViewState(latitude=10, longitude=0, zoom=1),
                tooltip={"text": "{astronomical_year} {month} {day}\nType: {eclipse_type_clean}"},
            ))
            st.caption(
                "Notice how each eclipse greatest-eclipse point shifts westward and drifts north/south compared to the previous one in the series - that drift is the Saros cycle's geometry slowly changing."
            )

### DATA TABLE TAB
with tab_table:
    st.subheader("Filtered data")
    display_cols = [
        "catalog_number", "astronomical_year", "month", "day",
        "eclipse_type_clean", "eclipse_type_suffix_raw", "saros_num",
        "magnitude", "latitude", "longitude", "path_width_km",
        "central_duration_seconds",
    ]
    if geography_available:
        display_cols += ["country_name", "continent", "is_likely_ocean"]

    display_cols = [c for c in display_cols if c in filtered.columns]
    table_df = filtered[display_cols].copy()
    table_df["NASA link"] = filtered.apply(build_nasa_link, axis=1)

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "NASA link": st.column_config.LinkColumn(
                "NASA link", display_text="View →"
            ),
        },
    )

    csv = filtered[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered data as CSV", csv,
                        "filtered_eclipses.csv", "text/csv")

st.divider()
st.caption(
    "Data: Five Millennium Catalog of Solar Eclipses. "
    "Eclipse Predictions by Fred Espenak (NASA's GSFC). "
    "Country/continent (when shown) are approximate, based on the nearest "
    "populated place to the point of greatest eclipse, not the full path."
)

### ABOUT TAB
with tab_about:
    st.subheader("About this project")
    st.markdown(
        "This dashboard explores solar eclipses from NASA's **Five Millennium Catalog of Solar Eclipses**, compiled by Fred Espenak (NASA's GSFC). "
        "Data is scraped from [eclipse.gsfc.nasa.gov](https://eclipse.gsfc.nasa.gov), "
        "cleaned, and loaded into a local SQLite database."
    )

    st.subheader("NASA's Solar Eclipse Atlas")
    st.caption(
        "Reference maps from NASA's own eclipse atlas series, shown here for "
        "context alongside the interactive map above. Pick a period below."
    )

    ATLASES = [
        {"label": "2001–2020", "filename": "SEatlas2001.gif",
         "url": "https://eclipse.gsfc.nasa.gov/SEatlas/SEatlas3/SEatlas2001.GIF"},
        {"label": "2021–2040", "filename": "SEatlas2021.gif",
         "url": "https://eclipse.gsfc.nasa.gov/SEatlas/SEatlas3/SEatlas2021.GIF"},
        {"label": "2041–2060", "filename": "SEatlas2041.gif",
         "url": "https://eclipse.gsfc.nasa.gov/SEatlas/SEatlas3/SEatlas2041.GIF"},
        {"label": "2061–2080", "filename": "SEatlas2061.gif",
         "url": "https://eclipse.gsfc.nasa.gov/SEatlas/SEatlas3/SEatlas2061.GIF"},
        {"label": "2081–2100", "filename": "SEatlas2081.gif",
         "url": "https://eclipse.gsfc.nasa.gov/SEatlas/SEatlas3/SEatlas2081.GIF"},
    ]

    if "selected_atlas_index" not in st.session_state:
        st.session_state.selected_atlas_index = 1  # default to 2021-2040

    button_cols = st.columns(len(ATLASES))
    for i, (col, atlas) in enumerate(zip(button_cols, ATLASES)):
        # Highlight the currently selected period's button
        button_type = "primary" if i == st.session_state.selected_atlas_index else "secondary"
        if col.button(atlas["label"], key=f"atlas_btn_{i}", type=button_type,
                       use_container_width=True):
            st.session_state.selected_atlas_index = i

    selected = ATLASES[st.session_state.selected_atlas_index]
    local_image_path = os.path.join("assets", selected["filename"])

    if os.path.isfile(local_image_path):
        st.image(local_image_path, caption=f"Eclipse Atlas {selected['label']} (NASA/GSFC)")
    else:
        try:
            st.image(selected["url"], caption=f"Eclipse Atlas {selected['label']} (NASA/GSFC)")
        except Exception:
            st.warning(
                f"Couldn't load this image from NASA server. Save a local copy to `{local_image_path}` to display it reliably instead."
            )
            
    st.caption(
        '"Eclipse Predictions by Fred Espenak and Jean Meeus (NASA\'s GSFC)" — '
        "reproduced here with attribution as permitted by NASA/GSFC."
    )