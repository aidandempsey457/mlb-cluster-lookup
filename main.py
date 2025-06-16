import os
import pandas as pd
import streamlit as st

# === STREAMLIT PAGE CONFIG ===
st.set_page_config(page_title="MLB Batter vs Pitcher Cluster Lookup", layout="centered")

# === STEP 1: Locate Latest Excel File from /output ===
default_excel_filename = None
output_dir = "output"

if not os.path.exists(output_dir):
    st.error("❌ 'output' folder not found. Please ensure it exists and contains the Excel file.")
    st.stop()

# Look for the most recent relational_cluster_2025_*.xlsx file
for f in sorted(os.listdir(output_dir), reverse=True):
    if f.startswith("relational_cluster_2025_") and f.endswith(".xlsx"):
        default_excel_filename = os.path.join(output_dir, f)
        break

if not default_excel_filename:
    st.error("❌ No Excel file found in 'output'. Expected file like: relational_cluster_2025_YYYY-MM-DD.xlsx")
    st.stop()

# === STEP 2: Load Excel Data ===
try:
    batter_vs_cluster = pd.read_excel(default_excel_filename, sheet_name="Batter vs Cluster")
    pitchers = pd.read_excel(default_excel_filename, sheet_name="Pitcher Clusters")
except Exception as e:
    st.error(f"❌ Failed to load Excel data: {e}")
    st.stop()

# === STEP 3: Streamlit App UI ===
st.title("⚾ Batter vs Pitcher Cluster Lookup")

st.markdown("Enter a **pitcher name** and a **team abbreviation** to view how that team’s hitters have performed against that pitcher's cluster.")

pitcher_name = st.text_input("🎯 Pitcher Full Name (e.g. Gerrit Cole)")
team_abbr = st.text_input("🏟️ Opponent Team Abbreviation (e.g. NYY)").upper()

if pitcher_name and team_abbr:
    matched = pitchers[pitchers['player_name'].str.lower() == pitcher_name.lower()]
    if matched.empty:
        st.error(f"No pitcher found with name: {pitcher_name}")
    else:
        cluster_id = matched.iloc[0]['cluster']
        st.success(f"✅ {pitcher_name} is in Cluster {cluster_id}")

        filtered = batter_vs_cluster[
            (batter_vs_cluster['cluster'] == cluster_id) &
            (batter_vs_cluster['team'] == team_abbr)
        ]

        if filtered.empty:
            st.warning("No batters found for this team vs that cluster.")
        else:
            st.markdown("### 📊 Batter Matchups vs This Pitcher Cluster")
            st.dataframe(
                filtered[['batter_full_name', 'BA', 'SLG', 'proxy_WAR', 'PA', 'Hits']].sort_values(
                    by='proxy_WAR', ascending=False
                )
            )
            