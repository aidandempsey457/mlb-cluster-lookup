import os
import pandas as pd
import numpy as np
from datetime import date
from sklearn.impute import KNNImputer
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
import umap
from pybaseball import statcast, playerid_reverse_lookup

# === STEP 0: Setup Safe Paths ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(SCRIPT_DIR, "data")
output_dir = os.path.join(SCRIPT_DIR, "output")
os.makedirs(data_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# === STEP 1: Pull and Save Statcast Data ===
start_date = "2025-03-20"
today = date.today().strftime("%Y-%m-%d")
data_filename = f"statcast_2025_through_{today}.xlsx"
data_path = os.path.join(data_dir, data_filename)

print(f"📡 Pulling Statcast data from {start_date} to {today}...")
df = statcast(start_dt=start_date, end_dt=today)
df.to_excel(data_path, index=False)
print(f"✅ Saved raw Statcast data to: {data_path}")

# === STEP 2: Load Excel Data ===
df = pd.read_excel(data_path)
df = df[df['pitch_type'].notna()]

# === STEP 3: Pitcher Feature Engineering ===
features = [
    'pitcher', 'pitch_type', 'release_speed', 'release_pos_x', 'release_pos_y', 'release_pos_z',
    'release_extension', 'pfx_x', 'pfx_z', 'release_spin_rate', 'spin_axis',
    'api_break_z_with_gravity', 'api_break_x_batter_in', 'arm_angle'
]
df_pitch = df[features].dropna()
grouped = df_pitch.groupby(['pitcher', 'pitch_type']).mean().reset_index()
pivoted = grouped.pivot(index='pitcher', columns='pitch_type')
pivoted.columns = [f'{stat}_{ptype}' for stat, ptype in pivoted.columns]
pivoted.reset_index(inplace=True)

# === STEP 4: UMAP + KMeans Clustering ===
pitcher_ids = pivoted[['pitcher']]
X = pivoted.drop(columns=['pitcher'])
X_scaled = StandardScaler().fit_transform(KNNImputer(n_neighbors=5).fit_transform(X))
X_umap = umap.UMAP(n_neighbors=15, min_dist=0.1, random_state=42).fit_transform(X_scaled)
clusters = KMeans(n_clusters=15, random_state=42).fit_predict(X_scaled)

result = pitcher_ids.copy()
result['cluster'] = clusters
result['UMAP_1'] = X_umap[:, 0]
result['UMAP_2'] = X_umap[:, 1]
result = result.merge(df[['pitcher', 'player_name']].drop_duplicates(), on='pitcher', how='left')
df = df.merge(result[['pitcher', 'cluster']], on='pitcher', how='inner')

# === STEP 5: Outcome Flags ===
df['BB'] = (df['events'] == 'walk').astype(int)
df['HBP'] = (df['events'] == 'hit_by_pitch').astype(int)
df['SF'] = (df['events'] == 'sac_fly').astype(int)

# === STEP 6: Batter vs Cluster Aggregates ===
valid_ab_events = ['single', 'double', 'triple', 'home_run', 'strikeout', 'field_out',
                   'grounded_into_double_play', 'force_out', 'strikeout_double_play', 'other_out']
hit_events = ['single', 'double', 'triple', 'home_run']

outcome_cols = [
    'batter', 'pitcher', 'cluster', 'events', 'estimated_ba_using_speedangle',
    'estimated_woba_using_speedangle', 'woba_value', 'woba_denom',
    'babip_value', 'iso_value', 'launch_speed_angle', 'launch_speed', 'launch_angle',
    'BB', 'HBP', 'SF'
]
batter_data = df[outcome_cols].dropna()
group = batter_data.groupby(['batter', 'cluster'])
batter_vs_cluster = group.agg(
    estimated_ba_using_speedangle=('estimated_ba_using_speedangle', 'mean'),
    estimated_woba_using_speedangle=('estimated_woba_using_speedangle', 'mean'),
    woba_value=('woba_value', 'mean'),
    woba_denom=('woba_denom', 'mean'),
    babip_value=('babip_value', 'mean'),
    iso_value=('iso_value', 'mean'),
    launch_speed_angle=('launch_speed_angle', 'mean'),
    max_launch_speed=('launch_speed', 'max'),
    avg_launch_angle=('launch_angle', 'mean'),
    pitches_faced=('events', 'count'),
    AB=('events', lambda x: x[x.isin(valid_ab_events)].count()),
    Hits=('events', lambda x: x[x.isin(hit_events)].count()),
    BB=('BB', 'sum'),
    HBP=('HBP', 'sum'),
    SF=('SF', 'sum')
).reset_index()

# === STEP 7: Derived Stats ===
batter_vs_cluster = batter_vs_cluster[batter_vs_cluster['AB'] >= 10]
batter_vs_cluster['BA'] = batter_vs_cluster['Hits'] / batter_vs_cluster['AB']
batter_vs_cluster['SLG'] = batter_vs_cluster['Hits'] / batter_vs_cluster['AB']
batter_vs_cluster['wOBA'] = batter_vs_cluster['woba_value'] / batter_vs_cluster['woba_denom']
batter_vs_cluster['PA'] = batter_vs_cluster['AB'] + batter_vs_cluster['BB'] + batter_vs_cluster['HBP'] + batter_vs_cluster['SF']
batter_vs_cluster['wRAA'] = ((batter_vs_cluster['wOBA'] - 0.315) / 1.25) * batter_vs_cluster['PA']
batter_vs_cluster['proxy_WAR'] = batter_vs_cluster['wRAA'] / 10

# === STEP 8: Cluster Rankings ===
strength = batter_vs_cluster.groupby('cluster')['wOBA'].mean().rank(method='dense', ascending=False)
batter_vs_cluster['cluster_tier'] = batter_vs_cluster['cluster'].map(strength)
batter_vs_cluster['cluster_rank'] = batter_vs_cluster.groupby('batter')['wOBA'].rank(ascending=False)

# === STEP 9: Team Mapping ===
df['batter_team'] = df.apply(lambda row: row['away_team'] if row['inning_topbot'] == 'Top' else row['home_team'], axis=1)
df['pitcher_team'] = df.apply(lambda row: row['home_team'] if row['inning_topbot'] == 'Top' else row['away_team'], axis=1)
batter_team_map = df.groupby('batter')['batter_team'].agg(lambda x: x.value_counts().idxmax()).to_dict()
pitcher_team_map = df.groupby('pitcher')['pitcher_team'].agg(lambda x: x.value_counts().idxmax()).to_dict()
batter_vs_cluster['team'] = batter_vs_cluster['batter'].map(batter_team_map)
result['team'] = result['pitcher'].map(pitcher_team_map)

# === STEP 10: Normalize Teams ===
teams = sorted(set(batter_vs_cluster['team'].dropna().unique()).union(result['team'].dropna().unique()))
team_df = pd.DataFrame({'team_ID': range(1, len(teams)+1), 'team': teams})
team_lookup = dict(zip(team_df['team'], team_df['team_ID']))
batter_vs_cluster['team_ID'] = batter_vs_cluster['team'].map(team_lookup)
result['team_ID'] = result['team'].map(team_lookup)

# === STEP 11: Add Batter & Pitcher Names ===
batter_names = playerid_reverse_lookup(batter_vs_cluster['batter'].unique(), key_type='mlbam')
batter_table = pd.merge(
    batter_vs_cluster[['batter', 'team_ID']].drop_duplicates(),
    batter_names[['key_mlbam', 'name_first', 'name_last']],
    left_on='batter', right_on='key_mlbam', how='left'
)
batter_table['batter_full_name'] = batter_table['name_first'] + ' ' + batter_table['name_last']
batter_table = batter_table[['batter', 'batter_full_name', 'team_ID']].drop_duplicates()

pitcher_names = playerid_reverse_lookup(result['pitcher'].unique(), key_type='mlbam')
pitcher_table = pd.merge(
    result[['pitcher', 'team_ID']].drop_duplicates(),
    pitcher_names[['key_mlbam', 'name_first', 'name_last']],
    left_on='pitcher', right_on='key_mlbam', how='left'
)
pitcher_table['pitcher_full_name'] = pitcher_table['name_first'] + ' ' + pitcher_table['name_last']
pitcher_table = pitcher_table[['pitcher', 'pitcher_full_name', 'team_ID']].drop_duplicates()

# === STEP 12: Merge Names and Round Metrics ===
batter_vs_cluster = batter_vs_cluster.merge(
    batter_table[['batter', 'batter_full_name']], on='batter', how='left'
)

cols_to_round = [
    'estimated_ba_using_speedangle', 'estimated_woba_using_speedangle',
    'woba_value', 'woba_denom', 'babip_value', 'iso_value', 'launch_speed_angle',
    'max_launch_speed', 'avg_launch_angle', 'BA', 'SLG', 'wOBA', 'wRAA', 'proxy_WAR'
]
batter_vs_cluster[cols_to_round] = batter_vs_cluster[cols_to_round].round(3)

# === STEP 13: Focused Output & Definitions ===
focused_batter_metrics = batter_vs_cluster[[
    'batter_full_name', 'team', 'cluster', 'proxy_WAR', 'PA', 'Hits', 'BA', 'SLG'
]].copy()

definitions = {
    "estimated_ba_using_speedangle": "Expected batting average based on exit velocity and launch angle.",
    "estimated_woba_using_speedangle": "Expected wOBA using speed and angle of the ball off bat.",
    "woba_value": "Weighted On-Base Average value for the event.",
    "woba_denom": "Denominator for wOBA calculation (plate appearances considered).",
    "babip_value": "Batting Average on Balls In Play.",
    "iso_value": "Isolated Power = SLG - BA, measures extra bases per at-bat.",
    "launch_speed_angle": "Optimized metric for scoring using launch speed and angle.",
    "max_launch_speed": "Maximum exit velocity (mph) for this batter vs cluster.",
    "avg_launch_angle": "Average angle the ball was hit, in degrees.",
    "SLG": "Slugging Percentage: total bases / at-bats.",
    "wOBA": "Weighted On-Base Average: more accurate than OBP for measuring value.",
    "wRAA": "Weighted Runs Above Average: run value created above league avg.",
    "proxy_WAR": "Estimated WAR proxy using wRAA / 10."
}
definitions_df = pd.DataFrame(list(definitions.items()), columns=["Metric", "Definition"])

# === STEP 14: Save All Outputs ===
output_file = os.path.join(output_dir, f"relational_cluster_2025_{today}.xlsx")
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    result.to_excel(writer, sheet_name="Pitcher Clusters", index=False)
    batter_vs_cluster.to_excel(writer, sheet_name="Batter vs Cluster", index=False)
    team_df.to_excel(writer, sheet_name="Teams", index=False)
    batter_table.to_excel(writer, sheet_name="Batters", index=False)
    pitcher_table.to_excel(writer, sheet_name="Pitchers", index=False)
    focused_batter_metrics.to_excel(writer, sheet_name="Focused batter metrics", index=False)
    definitions_df.to_excel(writer, sheet_name="Metric Definitions", index=False)

print(f"\n✅ Final Excel with enhancements saved to:\n{output_file}")
