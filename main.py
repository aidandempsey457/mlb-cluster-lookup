import os
import pandas as pd
import streamlit as st

# === STEP 1: Dynamically Locate Excel File in output/ ===
excel_path = None
output_folder = "output"
if os.path.exists(output_folder):
    for f in os.listdir(output_folder):
        if f.startswith("relational_cluster_2025_") and f.endswith(".xlsx"):
            excel_path = os.path.join(output_folder, f)
            break

if not excel_path:
    st.error("❌ No Excel file found in output/. Please run the pipeline script first.")
    st.stop()

# === STEP 2: Load Excel Sheets ===
try:
    batter_vs_cluster = pd.read_excel(excel_path, sheet_name="Batter vs Cluster")
    pitchers = pd.read_excel(excel_path, sheet_name="Pitcher Clusters")
except Exception as e:
    st.error(f"❌ Failed to load data from Excel file: {e}")
    st.stop()

# === STEP 3: Streamlit UI ===
st.title("⚾️ Batter vs Pitcher Cluster Lookup")

pitcher_name = st.text_input("Enter Pitcher Full Name (e.g. Gerrit Cole)")
team_abbr = st.text_input("Enter Opponent Team Abbreviation (e.g. NYY)").upper()

if pitcher_name and team_abbr:
    try:
        matched = pitchers[pitchers['player_name'].str.lower() == pitcher_name.lower()]
        if matched.empty:
            st.error(f"No pitcher found for name: {pitcher_name}")
        else:
            cluster_id = matched.iloc[0]['cluster']
            st.success(f"{pitcher_name} is in Cluster {cluster_id}")

            filtered = batter_vs_cluster[
                (batter_vs_cluster['cluster'] == cluster_id) &
                (batter_vs_cluster['team'] == team_abbr)
            ]

            if filtered.empty:
