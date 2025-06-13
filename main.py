import os
import pandas as pd
import streamlit as st

# === SETTINGS ===
default_excel_filename = None

# === STEP 1: Dynamically Locate Excel File ===
for f in os.listdir():
    if f.startswith("relational_cluster_2025_") and f.endswith(".xlsx"):
        default_excel_filename = f
        break

if not default_excel_filename:
    st.error("❌ No Excel file found. Please upload a file named like: relational_cluster_2025_YYYY-MM-DD.xlsx")
    st.stop()

# === STEP 2: Load Excel Sheets ===
try:
    batter_vs_cluster = pd.read_excel(default_excel_filename, sheet_name="Batter vs Cluster")
    pitchers = pd.read_excel(default_excel_filename, sheet_name="Pitcher Clusters")
except Exception as e:
    st.error(f"❌ Failed to load data from Excel: {e}")
    st.stop()

# === STEP 3: User Interface ===
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
                st.warning("No batter matchups found for this team vs that cluster.")
            else:
                st.dataframe(filtered[['batter_full_name', 'BA', 'SLG', 'proxy_WAR', 'PA', 'Hits']].sort_values(by='proxy_WAR', ascending=False))

    except Exception as e:
        st.error(f"Error during lookup: {e}")
