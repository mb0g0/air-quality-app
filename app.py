
# Run with: streamlit run app.py

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
    st.success("✅ Plan saved to database!")

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

# Initialize database on app start
init_db()

# === PAGE CONFIGURATION ===
st.set_page_config(page_title="Air Quality Planner", layout="centered")
st.title("🌤️ Air Quality Activity Planner")
st.markdown("Enter a city and your planned activities — get the **best times** based on air quality forecast.")

# === SIDEBAR: View Saved Plans ===
with st.sidebar:
    st.header("📂 Saved Plans")
    plans_history = load_all_plans()
    if not plans_history.empty:
        selected_id = st.selectbox(
            "Choose a past plan to reload",
            options=plans_history["id"].tolist(),
            format_func=lambda pid: f"{plans_history[plans_history['id']==pid]['created_at'].values[0]} — {plans_history[plans_history['id']==pid]['city'].values[0]}"
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
        st.info("No saved plans yet. Generate and save one!")

# === USER INPUTS ===
col1, col2 = st.columns(2)
with col1:
    default_city = st.session_state.get("loaded_city", "London")
    city = st.text_input("City", value=default_city)
with col2:
    default_country = st.session_state.get("loaded_country", "UK")
    country = st.text_input("Country (optional)", value=default_country)

default_activities = st.session_state.get("loaded_activities", ["Running outdoors", "Picnic in the park", "Indoor yoga", "Cycling"])
activities_input = st.text_area(
    "Activities (one per line)",
    value="\n".join(default_activities),
    height=150
)
activities = [line.strip() for line in activities_input.strip().split("\n") if line.strip()]

# === AQI COLOR HELPER ===
def aqi_color(aqi: int) -> str:
    colors = ["#10b981", "#22c55e", "#f59e0b", "#ef4444", "#991b1b"]  # Good → Very Poor
    return colors[aqi - 1] if 1 <= aqi <= 5 else "#gray"

# === FETCH AIR QUALITY DATA FROM OPENWEATHERMAP ===
@st.cache_data(ttl=1800)  # Cache for 30 minutes
def get_aqi_data(city_name: str, country_code: str = "") -> tuple[pd.DataFrame, str]:
    api_key = st.secrets["OPENWEATHER_API_KEY"]

    # Step 1: Geocode city
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name},{country_code}".strip(","), "limit": 1, "appid": api_key}
    try:
        geo_resp = requests.get(geo_url, params=geo_params, timeout=10).json()
        if not geo_resp:
            return None, "City not found. Try adding a country code."
        lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
    except Exception:
        return None, "Failed to geocode city."

    # Step 2: Get AQI forecast
    aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution/forecast"
    aqi_params = {"lat": lat, "lon": lon, "appid": api_key}
    try:
        data = requests.get(aqi_url, params=aqi_params, timeout=10).json()["list"][:24]  # Next 24 hours
        rows = []
        for entry in data:
            dt = datetime.fromtimestamp(entry["dt"])
            aqi = entry["main"]["aqi"]
            level = ["Good", "Fair", "Moderate", "Poor", "Very Poor"][aqi - 1]
            time_str = dt.strftime("%I %p").lstrip("0")  # e.g., "3 PM"
            rows.append({"time": time_str, "aqi": aqi, "level": level})
        return pd.DataFrame(rows), None
    except Exception:
        return None, "Failed to fetch air quality data."

# === RECOMMEND BEST TIMES ===
def recommend_times(activities_list: list, df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for activity in activities_list:
        is_outdoor = any(word in activity.lower() for word in ["outdoor", "run", "jog", "cycle", "bike", "picnic", "hike", "walk", "garden", "sport"])
        if is_outdoor:
            good_times = df[df["aqi"] <= 2]["time"].tolist()  # Good or Fair
            best_time = ", ".join(good_times) if good_times else "No safe time today"
        else:
            best_time = "Any time (indoor activity)"
        results.append({"Activity": activity, "Best Time": best_time})
    return pd.DataFrame(results)

# === MAIN APP LOGIC ===
if st.button("Get Best Times", type="primary"):
    if not activities:
        st.error("Please enter at least one activity.")
    else:
        with st.spinner("Fetching air quality forecast..."):
            aqi_df, error = get_aqi_data(city, country)
            if error:
                st.error(error)
            else:
                st.success(f"✅ Forecast loaded for **{city}**")

                # AQI Chart
                st.subheader("Air Quality Forecast (Next 24 Hours)")
                fig, ax = plt.subplots(figsize=(11, 4.5))
                ax.bar(aqi_df["time"], aqi_df["aqi"],
                       color=[aqi_color(v) for v in aqi_df["aqi"]],
                       edgecolor="black", linewidth=0.7)
                ax.set_ylim(0, 5)
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_yticklabels(["Good", "Fair", "Moderate", "Poor", "Very Poor"])
                ax.set_ylabel("AQI Level")
                ax.set_xlabel("Time of Day")
                plt.xticks(rotation=45, ha="right")
                plt.tight_layout()
                st.pyplot(fig)

                # Color Legend
                st.markdown("""
                <div style="display:flex; gap:12px; margin:20px 0; font-weight:500;">
                  <span style="background:#10b981;color:white;padding:4px 10px;border-radius:4px;">Good</span>
                  <span style="background:#22c55e;color:white;padding:4px 10px;border-radius:4px;">Fair</span>
                  <span style="background:#f59e0b;color:black;padding:4px 10px;border-radius:4px;">Moderate</span>
                  <span style="background:#ef4444;color:white;padding:4px 10px;border-radius:4px;">Poor</span>
                  <span style="background:#991b1b;color:white;padding:4px 10px;border-radius:4px;">Very Poor</span>
                </div>
                <p><strong>Best for outdoor activities → Green/Fair</strong> | Avoid outdoors → Red</p>
                """, unsafe_allow_html=True)

                # Recommendation Table
                st.subheader("Your Personalized Activity Plan")
                plan = recommend_times(activities, aqi_df)

                # Fixed row styling (prevents errors with "Any time" or "No safe time")
                def style_row(row):
                    best_time = row["Best Time"]
                    if "Any time" in best_time or "No safe" in best_time:
                        return [""] * len(row)
                    times = [t.strip() for t in best_time.split(",")]
                    matching = aqi_df[aqi_df["time"].isin(times)]["aqi"]
                    avg_aqi = int(matching.mean()) if not matching.empty else 3
                    color = aqi_color(avg_aqi)
                    return [f"background-color: {color}; opacity: 0.8"] * len(row)

                styled_plan = plan.style.apply(style_row, axis=1)
                st.dataframe(styled_plan, hide_index=True, use_container_width=True)

                # Save to DB & Download CSV
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 Save This Plan to Database", type="secondary"):
                        save_plan(city, country, activities, plan)
                with col2:
                    csv_data = plan.to_csv(index=False).encode()
                    st.download_button(
                        label="📄 Download Plan as CSV",
                        data=csv_data,
                        file_name=f"air_quality_plan_{city.lower()}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )

                # Clear loaded session state after display
                for key in ["loaded_plan", "loaded_activities", "loaded_city", "loaded_country"]:
                    st.session_state.pop(key, None)
