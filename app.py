import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt

# === CONFIG ===
st.set_page_config(page_title="Air Quality Planner", layout="centered")
st.title("Air Quality Activity Planner")
st.markdown("Enter a city + activities → get **best times** based on air quality.")

# === USER INPUTS ===
col1, col2 = st.columns(2)
with col1:
    city = st.text_input("City", "London", help="e.g., Paris, Tokyo")
with col2:
    country = st.text_input("Country (optional)", "UK", help="e.g., FR, JP")

activities_input = st.text_area(
    "Activities (one per line)",
    "Running outdoors\nPicnic in the park\nIndoor yoga\nCycling",
    height=120
)
activities = [a.strip() for a in activities_input.strip().split("\n") if a.strip()]

# === HELPER: AQI COLOR ===
def aqi_color(aqi: int) -> str:
    """Return hex color for AQI 1-5 (Good → Very Poor)"""
    colors = ["#10b981", "#22c55e", "#f59e0b", "#ef4444", "#991b1b"]
    return colors[aqi - 1]

# === FETCH AQI DATA ===
@st.cache_data(ttl=1800)  # Cache for 30 minutes
def get_aqi(city_name, country_code=""):
    api_key = st.secrets.get("OPENWEATHER_API_KEY")
    if not api_key:
        return None, "API key missing. Add it in Streamlit Secrets."

    # Geocode city
    geo_url = "http://api.openweathermap.org/geo/1.0/direct"
    geo_params = {"q": f"{city_name},{country_code}", "limit": 1, "appid": api_key}
    try:
        geo_resp = requests.get(geo_url, params=geo_params).json()
        if not geo_resp:
            return None, "City not found. Try adding country."
        lat, lon = geo_resp[0]["lat"], geo_resp[0]["lon"]
    except Exception as e:
        return None, f"Geocoding error: {e}"

    # Get air quality forecast
    aqi_url = "http://api.openweathermap.org/data/2.5/air_pollution/forecast"
    aqi_params = {"lat": lat, "lon": lon, "appid": api_key}
    try:
        data = requests.get(aqi_url, params=aqi_params).json()["list"][:24]  # Next 24 hours
        rows = []
        for entry in data:
            dt = datetime.fromtimestamp(entry["dt"])
            aqi = entry["main"]["aqi"]
            level = ["Good", "Fair", "Moderate", "Poor", "Very Poor"][aqi - 1]
            time_str = dt.strftime("%I %p").lstrip("0")
            rows.append({"time": time_str, "aqi": aqi, "level": level})
        return pd.DataFrame(rows), None
    except Exception as e:
        return None, f"Air quality fetch error: {e}"

# === RECOMMEND TIMES ===
def recommend(activities, df):
    results = []
    for act in activities:
        is_outdoor = any(word in act.lower() for word in [
            "outdoor", "run", "jog", "cycle", "bike", "picnic", "hike", "walk", "garden"
        ])
        if is_outdoor:
            good_times = df[df["aqi"] <= 2]["time"].tolist()
            best_time = ", ".join(good_times) if good_times else "No safe time"
        else:
            best_time = "Any time"
        results.append({"Activity": act, "Best Time": best_time})
    return pd.DataFrame(results)

# === MAIN LOGIC ===
if st.button("Get Best Times", type="primary"):
    if not activities:
        st.error("Please add at least one activity.")
    else:
        with st.spinner("Fetching air quality data..."):
            df, error = get_aqi(city, country)
            if error:
                st.error(error)
            else:
                st.success(f"Data loaded for **{city}**")

                # === AQI FORECAST CHART ===
                st.subheader("AQI Forecast (Next 24 Hours)")
                fig, ax = plt.subplots(figsize=(10, 4))
                bars = ax.bar(
                    df["time"], df["aqi"],
                    color=[aqi_color(v) for v in df["aqi"]],
                    edgecolor="black", linewidth=0.8
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
                <div style="display:flex; gap:12px; margin-top:10px; font-size:0.9rem; font-weight:500;">
                  <span style="background:#10b981;color:white;padding:3px 8px;border-radius:4px;">Good</span>
                  <span style="background:#22c55e;color:white;padding:3px 8px;border-radius:4px;">Fair</span>
                  <span style="background:#f59e0b;color:black;padding:3px 8px;border-radius:4px;">Moderate</span>
                  <span style="background:#ef4444;color:white;padding:3px 8px;border-radius:4px;">Poor</span>
                  <span style="background:#991b1b;color:white;padding:3px 8px;border-radius:4px;">Very Poor</span>
                </div>
                <p style="margin-top:8px; font-size:0.85rem; color:#666;">
                  <strong>Best</strong> → Good/Fair (green) | <strong>Worst</strong> → Poor/Very Poor (red)
                </p>
                """
                st.markdown(legend_html, unsafe_allow_html=True)

                # === RECOMMENDATION TABLE ===
                st.subheader("Your Activity Plan")
                plan = recommend(activities, df)

                # Add average AQI for row coloring
                def avg_aqi(time_str):
                    if "any time" in time_str.lower() or "no safe" in time_str.lower():
                        return 0
                    times = [t.strip() for t in time_str.split(",")]
                    matching = df[df["time"].isin(times)]["aqi"]
                    return int(matching.mean()) if not matching.empty else 0

                plan["AQI"] = plan["Best Time"].apply(avg_aqi)

                # Style rows by AQI
                def color_row(row):
                    if row["AQI"] == 0:
                        return [""] * len(row)
                    return [f"background-color: {aqi_color(row['AQI'])}"] * len(row)

                styled_plan = plan.style.apply(color_row, axis=1).format({"AQI": "{:.0f}"})
                st.dataframe(styled_plan, hide_index=True, use_container_width=True)

                # === DOWNLOAD ===
                csv = plan.drop(columns=["AQI"]).to_csv(index=False).encode()
                st.download_button(
                    label="Download Plan as CSV",
                    data=csv,
                    file_name="air_quality_activity_plan.csv",
                    mime="text/csv"
                )
