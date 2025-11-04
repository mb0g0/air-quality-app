# app.py - Air Quality Activity Planner
# Run locally with: streamlit run app.py

import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt  # ← REQUIRED FOR CHARTS

# === PAGE SETUP ===
st.set_page_config(page_title="Air Quality Planner", layout="centered")
st.title("Air Quality Activity Planner")
st.markdown("Enter a city and your activities → get **best times** based on air quality.")

# === USER INPUTS ===
col1, col2 = st.columns(2)
with col1:
    city = st.text_input("City", value="London", placeholder="e.g., Tokyo")
with col2:
    country = st.text_input("Country (optional)", value="UK", placeholder="e.g., JP")

activities_input = st.text_area(
    "Activities (one per line)",
    value="Running outdoors\nPicnic in the park\nIndoor yoga\nCycling",
    height=130
)
activities = [line.strip() for line in activities_input.strip().split("\n") if line.strip()]

# === AQI COLOR HELPER ===
def aqi_color(aqi: int) -> str:
    """Return hex color for AQI level 1-5"""
    colors = ["#10b981", "#22c55e", "#f59e0b", "#ef4444", "#991b1b"]  # Good → Very Poor
    return colors[aqi - 1]

# === FETCH AIR QUALITY DATA ===
@st.cache_data(ttl=1800)  # Cache for 30 minutes
def get_aqi_data(city_name: str, country_code: str = "") -> tuple:
    api_key = st.secrets.get("OPENWEATHER_API_KEY")
    if not api_key:
        return None, "Missing API key. Add to `.streamlit/secrets.toml` (local) or Streamlit Secrets (cloud)."

    # Step 1: Geocode city
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name},{country_code}", "limit": 1, "appid": api_key}
    try:
        geo_data = requests.get(geo_url, params=geo_params).json()
        if not geo_data:
            return None, "City not found. Try adding country code."
        lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
    except Exception:
        return None, "Failed to find city."

    # Step 2: Get AQI forecast
    aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution/forecast"
    aqi_params = {"lat": lat, "lon": lon, "appid": api_key}
    try:
        raw_data = requests.get(aqi_url, params=aqi_params).json()["list"][:24]  # Next 24h
        rows = []
        for entry in raw_data:
            dt = datetime.fromtimestamp(entry["dt"])
            aqi = entry["main"]["aqi"]
            level = ["Good", "Fair", "Moderate", "Poor", "Very Poor"][aqi - 1]
            time_str = dt.strftime("%I %p").lstrip("0")
            rows.append({"time": time_str, "aqi": aqi, "level": level})
        return pd.DataFrame(rows), None
    except Exception:
        return None, "Failed to fetch air quality data."

# === RECOMMEND BEST TIMES ===
def recommend_times(activities_list: list, df: pd.DataFrame) -> pd.DataFrame:
    results = []
    for activity in activities_list:
        is_outdoor = any(word in activity.lower() for word in [
            "outdoor", "run", "jog", "cycle", "bike", "picnic", "hike", "walk", "garden"
        ])
        if is_outdoor:
            good_times = df[df["aqi"] <= 2]["time"].tolist()
            best_time = ", ".join(good_times) if good_times else "No safe time"
        else:
            best_time = "Any time"
        results.append({"Activity": activity, "Best Time": best_time})
    return pd.DataFrame(results)

# === MAIN APP LOGIC ===
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

                # === AQI FORECAST CHART ===
                st.subheader("AQI Forecast (Next 24 Hours)")
                fig, ax = plt.subplots(figsize=(11, 4.5))
                ax.bar(
                    df["time"],
                    df["aqi"],
                    color=[aqi_color(val) for val in df["aqi"]],
                    edgecolor="black",
                    linewidth=0.7
                )
                ax.set_ylim(0, 5)
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_yticklabels(["Good", "Fair", "Moderate", "Poor", "Very Poor"])
                ax.set_ylabel("AQI Level")
                ax.set_xlabel("Time")
                plt.xticks(rotation=45, ha="right")
                plt.tight_layout()
                st.pyplot(fig)

                # === COLOR LEGEND ===
                legend_html = """
                <div style="display:flex; gap:12px; margin:12px 0; font-size:0.9rem; font-weight:500;">
                  <span style="background:#10b981;color:white;padding:3px 8px;border-radius:4px;">Good</span>
                  <span style="background:#22c55e;color:white;padding:3px 8px;border-radius:4px;">Fair</span>
                  <span style="background:#f59e0b;color:black;padding:3px 8px;border-radius:4px;">Moderate</span>
                  <span style="background:#ef4444;color:white;padding:3px 8px;border-radius:4px;">Poor</span>
                  <span style="background:#991b1b;color:white;padding:3px 8px;border-radius:4px;">Very Poor</span>
                </div>
                <p style="margin-top:6px; font-size:0.85rem; color:#666;">
                  <strong>Best</strong> → Green (Good/Fair) | <strong>Worst</strong> → Red (Poor/Very Poor)
                </p>
                """
                st.markdown(legend_html, unsafe_allow_html=True)

                # === RECOMMENDATION TABLE ===
                st.subheader("Your Activity Plan")
                plan = recommend_times(activities, df)

                # Add average AQI for row coloring
                def get_avg_aqi(time_str: str) -> int:
                    if "any time" in time_str.lower() or "no safe" in time_str.lower():
                        return 0
                    times = [t.strip() for t in time_str.split(",")]
                    matching = df[df["time"].isin(times)]["aqi"]
                    return int(matching.mean()) if not matching.empty else 0

                plan["AQI"] = plan["Best Time"].apply(get_avg_aqi)

                # Style rows
                def style_row(row):
                    if row["AQI"] == 0:
                        return [""] * len(row)
                    return [f"background-color: {aqi_color(row['AQI'])}"] * len(row)

                styled_plan = plan.style.apply(style_row, axis=1).format({"AQI": "{:.0f}"})
                st.dataframe(styled_plan, hide_index=True, use_container_width=True)

                # === DOWNLOAD CSV ===
                csv_data = plan.drop(columns=["AQI"]).to_csv(index=False).encode()
                st.download_button(
                    label="Download Plan as CSV",
                    data=csv_data,
                    file_name=f"activity_plan_{city.lower()}.csv",
                    mime="text/csv"
                )
