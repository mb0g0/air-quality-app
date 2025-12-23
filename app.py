# app.py - Air Quality Activity Planner with SQLite Database
import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import sqlite3
import json

# === DATABASE SETUP ===
DB_FILE = "air_quality_plans.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            country TEXT,
            activities TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_plan(city: str, country: str, activities: list, plan_df: pd.DataFrame):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO plans (city, country, activities, plan_json)
        VALUES (?, ?, ?, ?)
    """, (city, country or "", json.dumps(activities), plan_df.to_json()))
    conn.commit()
    conn.close()
    st.success("Plan saved to database!")

def load_all_plans() -> pd.DataFrame:
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT id, city, country, activities, created_at FROM plans ORDER BY created_at DESC", conn)
    conn.close()
    if not df.empty:
        df["activities"] = df["activities"].apply(lambda x: json.loads(x))
    return df

def load_plan_by_id(plan_id: int) -> tuple[pd.DataFrame, list, str, str]:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT city, country, activities, plan_json FROM plans WHERE id = ?", (plan_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        city, country, activities_json, plan_json = row
        activities = json.loads(activities_json)
        plan_df = pd.read_json(plan_json)
        return plan_df, activities, city, country or ""
    return None, None, None, None

# Initialize DB on app start
init_db()

# === PAGE SETUP ===
st.set_page_config(page_title="Air Quality Planner", layout="centered")
st.title("🌤️ Air Quality Activity Planner")
st.markdown("Enter a city and your activities → get **best times** based on air quality.")

# Sidebar for viewing history
with st.sidebar:
    st.header("📂 Saved Plans")
    plans_df = load_all_plans()
    if not plans_df.empty:
        selected_id = st.selectbox(
            "View a past plan",
            options=plans_df["id"],
            format_func=lambda pid: f"{plans_df[plans_df['id']==pid]['created_at'].iloc[0]} – {plans_df[plans_df['id']==pid]['city'].iloc[0]}"
        )
        if st.button("Load Selected Plan"):
            plan, acts, city_name, country_name = load_plan_by_id(selected_id)
            if plan is not None:
                st.session_state["loaded_plan"] = plan
                st.session_state["loaded_activities"] = acts
                st.session_state["loaded_city"] = city_name
                st.session_state["loaded_country"] = country_name
                st.rerun()
    else:
        st.info("No saved plans yet.")

# === USER INPUTS ===
col1, col2 = st.columns(2)
with col1:
    city = st.text_input("City", value=st.session_state.get("loaded_city", "London"))
with col2:
    country = st.text_input("Country (optional)", value=st.session_state.get("loaded_country", "UK"))

activities_input = st.text_area(
    "Activities (one per line)",
    value="\n".join(st.session_state.get("loaded_activities", ["Running outdoors", "Picnic in the park", "Indoor yoga", "Cycling"])),
    height=130
)
activities = [line.strip() for line in activities_input.strip().split("\n") if line.strip()]

# === AQI COLOR HELPER ===
def aqi_color(aqi: int) -> str:
    colors = ["#10b981", "#22c55e", "#f59e0b", "#ef4444", "#991b1b"]
    return colors[aqi - 1] if 1 <= aqi <= 5 else "#gray"

# === FETCH AIR QUALITY DATA (Direct from OpenWeatherMap using secrets) ===
@st.cache_data(ttl=1800)
def get_aqi_data(city_name: str, country_code: str = "") -> tuple:
    api_key = st.secrets["OPENWEATHER_API_KEY"]
    
    # Geocode
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name},{country_code}", "limit": 1, "appid": api_key}
    try:
        geo_data = requests.get(geo_url, params=geo_params).json()
        if not geo_data:
            return None, "City not found."
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
    except:
        return None, "Geocoding failed."

    # AQI Forecast
    aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution/forecast"
    aqi_params = {"lat": lat, "lon": lon, "appid": api_key}
    try:
        raw_data = requests.get(aqi_url, params=aqi_params).json()["list"][:24]
        rows = []
        for entry in raw_data:
            dt = datetime.fromtimestamp(entry["dt"])
            aqi = entry["main"]["aqi"]
            level = ["Good", "Fair", "Moderate", "Poor", "Very Poor"][aqi - 1]
            time_str = dt.strftime("%I %p").lstrip("0")
            rows.append({"time": time_str, "aqi": aqi, "level": level})
        return pd.DataFrame(rows), None
    except:
        return None, "Failed to fetch AQI data."

# === RECOMMEND BEST TIMES ===
def recommend_times(activities_list: list, df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for activity in activities_list:
        is_outdoor = any(word in activity.lower() for word in ["outdoor", "run", "jog", "cycle", "bike", "picnic", "hike", "walk", "garden"])
        if is_outdoor:
            good_times = df[df["aqi"] <= 2]["time"].tolist()
            best_time = ", ".join(good_times) if good_times else "No safe time"
        else:
            best_time = "Any time"
        results.append({"Activity": activity, "Best Time": best_time})
    return pd.DataFrame(results)

# === MAIN LOGIC ===
if st.button("Get Best Times", type="primary"):
    if not activities:
        st.error("Please enter at least one activity.")
    else:
        with st.spinner("Fetching air quality data..."):
            df, error = get_aqi_data(city, country)
            if error:
                st.error(error)
            else:
                st.success(f"Data loaded for **{city}**")

                # Chart
                st.subheader("AQI Forecast (Next 24 Hours)")
                fig, ax = plt.subplots(figsize=(11, 4.5))
                ax.bar(df["time"], df["aqi"], color=[aqi_color(v) for v in df["aqi"]], edgecolor="black")
                ax.set_ylim(0, 5)
                ax.set_yticks([1,2,3,4,5])
                ax.set_yticklabels(["Good", "Fair", "Moderate", "Poor", "Very Poor"])
                ax.set_ylabel("AQI Level")
                ax.set_xlabel("Time")
                plt.xticks(rotation=45, ha="right")
                plt.tight_layout()
                st.pyplot(fig)

                # Legend
                st.markdown("""
                <div style="display:flex; gap:12px; margin:12px 0;">
                  <span style="background:#10b981;color:white;padding:3px 8px;border-radius:4px;">Good</span>
                  <span style="background:#22c55e;color:white;padding:3px 8px;border-radius:4px;">Fair</span>
                  <span style="background:#f59e0b;color:black;padding:3px 8px;border-radius:4px;">Moderate</span>
                  <span style="background:#ef4444;color:white;padding:3px 8px;border-radius:4px;">Poor</span>
                  <span style="background:#991b1b;color:white;padding:3px 8px;border-radius:4px;">Very Poor</span>
                </div>
                """, unsafe_allow_html=True)

                # Recommendation Table
                st.subheader("Your Activity Plan")
                plan = recommend_times(activities, df)
                
                def style_row(row):
                    avg_aqi = df[df["time"].isin(row["Best Time"].split(", "))]["aqi"].mean() if "Any time" not in row["Best Time"] else 0
                    color = aqi_color(int(avg_aqi)) if avg_aqi > 0 else ""
                    return [f"background-color: {color}"] * len(row)
                
                styled_plan = plan.style.apply(style_row, axis=1)
                st.dataframe(styled_plan, hide_index=True, use_container_width=True)

                # Save to DB + Download
                col_save, col_dl = st.columns(2)
                with col_save:
                    if st.button("💾 Save This Plan to Database"):
                        save_plan(city, country, activities, plan)
                with col_dl:
                    csv = plan.to_csv(index=False).encode()
                    st.download_button(
                        "Download CSV",
                        csv,
                        f"plan_{city.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv"
                    )

                # Show loaded plan if any
                if "loaded_plan" in st.session_state:
                    st.info("You are viewing a previously saved plan.")
                    del st.session_state["loaded_plan"]
                    del st.session_state["loaded_activities"]
                    del st.session_state["loaded_city"]
                    del st.session_state["loaded_country"]
