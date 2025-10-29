import streamlit as st
import requests
import pandas as pd
from datetime import datetime
# ← UPDATE THIS PART  (add right after the other imports)
import matplotlib.pyplot as plt
import numpy as np

def aqi_color(aqi: int) -> str:
    """Return Tailwind-style hex color for AQI 1-5."""
    colors = ["#10b981", "#22c55e", "#f59e0b", "#ef4444", "#991b1b"]  # Good → Very Poor
    return colors[aqi - 1]

st.set_page_config(page_title="Air Quality Planner", layout="centered")
st.title("🌬️ Air Quality Activity Planner")
st.markdown("Enter a city + activities → get the **best times** based on air quality.")

# === INPUTS ===
col1, col2 = st.columns(2)
with col1:
    city = st.text_input("City", "London")
with col2:
    country = st.text_input("Country (optional)", "UK")

activities = st.text_area(
    "Activities (one per line)",
    "Running outdoors\nPicnic\nIndoor yoga\nCycling",
    height=120
).strip().split("\n")
activities = [a.strip() for a in activities if a.strip()]

# === FETCH AQI ===
@st.cache_data(ttl=1800)
def get_aqi(city, country=""):
    geo = requests.get(
        "http://api.openweathermap.org/geo/1.0/direct",
        params={"q": f"{city},{country}", "limit": 1, "appid": st.secrets.OPENWEATHER_API_KEY}
    ).json()
    if not geo: return None, "City not found"
    lat, lon = geo[0]["lat"], geo[0]["lon"]

    data = requests.get(
        "http://api.openweathermap.org/data/2.5/air_pollution/forecast",
        params={"lat": lat, "lon": lon, "appid": st.secrets.OPENWEATHER_API_KEY}
    ).json()["list"][:24]

    rows = []
    for d in data:
        dt = datetime.fromtimestamp(d["dt"])
        aqi = d["main"]["aqi"]
        level = ["Good", "Fair", "Moderate", "Poor", "Very Poor"][aqi-1]
        rows.append({"time": dt.strftime("%I %p").lstrip("0"), "aqi": aqi, "level": level})
    return pd.DataFrame(rows), None

# === RECOMMEND ===
def recommend(activities, df):
    res = []
    for act in activities:
        outdoor = any(w in act.lower() for w in ["outdoor","run","jog","cycle","bike","picnic","hike","walk","garden"])
        if outdoor:
            good = df[df["aqi"] <= 2]["time"].tolist()  # ← MUST BE INDENTED
            times = ", ".join(good) if good else "No safe time"
        else:
            times = "Any time"
        res.append({"Activity": act, "Best Time": times})
    return pd.DataFrame(res)

# === RUN ===
# === RUN ===
if st.button("Get Best Times", type="primary"):
    if not activities:
        st.error("Add at least one activity")
    else:
        with st.spinner("Checking air quality..."):
            df, err = get_aqi(city, country)
            if err:
                st.error(err)
            else:
                st.success(f"Data loaded for **{city}**")
                st.subheader("AQI Forecast (next 24 h)")

                # ---- Colored bar chart ----
                fig, ax = plt.subplots(figsize=(10, 4))
                bars = ax.bar(df["time"], df["aqi"],
                              color=[aqi_color(v) for v in df["aqi"]],
                              edgecolor="black", linewidth=0.8)
                ax.set_ylim(0, 5)
                ax.set_yticks([1,2,3,4,5])
                ax.set_yticklabels(["Good","Fair","Moderate","Poor","Very Poor"])
                ax.set_ylabel("AQI Level")
                ax.set_xlabel("Time")
                plt.xticks(rotation=45, ha="right")
                plt.tight_layout()
                st.pyplot(fig)

                # ---- Caption legend ----
                legend_html = """
                <div style="display:flex; gap:12px; margin-top:8px; font-size:0.9rem;">
                  <span style="background:#10b981;color:white;padding:2px 6px;border-radius:4px;">Good</span>
                  <span style="background:#22c55e;color:white;padding:2px 6px;border-radius:4px;">Fair</span>
                  <span style="background:#f59e0b;color:black;padding:2px 6px;border-radius:4px;">Moderate</span>
                  <span style="background:#ef4444;color:white;padding:2px 6px;border-radius:4px;">Poor</span>
                  <span style="background:#991b1b;color:white;padding:2px 6px;border-radius:4px;">Very Poor</span>
                </div>
                """
                st.markdown(legend_html, unsafe_allow_html=True)

# ←←←← THIS IS OUTSIDE THE 'with' BLOCK (NO INDENT!)
st.subheader("Your Plan")
plan = recommend(activities, df)

# Add average AQI for coloring
def avg_aqi(times_str: str) -> int:
    if "any time" in times_str.lower() or "no safe" in times_str.lower():
        return 0
    times = [t.strip() for t in times_str.split(",")]
    matching = df[df["time"].isin(times)]["aqi"]
    return int(matching.mean()) if not matching.empty else 0

plan["AQI"] = plan["Best Time"].apply(avg_aqi)

def color_row(row):
    if row["AQI"] == 0:
        return [""] * len(row)
    return [f"background-color: {aqi_color(row['AQI'])}"] * len(row)

styled = plan.style.apply(color_row, axis=1).format({"AQI": "{:.0f}"})
st.dataframe(styled, hide_index=True, use_container_width=True)

st.download_button(
    "Download Plan",
    plan.drop(columns=["AQI"]).to_csv(index=False),
    "plan.csv",
    "text/csv"
)           st.download_button("📥 Download", plan.to_csv(index=False), "plan.csv", "text/csv")
