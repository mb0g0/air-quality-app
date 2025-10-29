import streamlit as st
import requests
import pandas as pd
from datetime import datetime

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
def recommend(acts, df):
    res = []
    for act in acts:
        outdoor = any(w in act.lower() for w in ["outdoor","run","jog","cycle","bike","picnic","hike","walk","garden"])
        if outdoor:
            good = df[df["aqi"] <= 2]["time"].tolist()
            times = ", ".join(good) if good else "No safe time"
        else:
            times = "Any time"
        res.append({"Activity": act, "Best Time": times})
    return pd.DataFrame(res)

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
                st.subheader("AQI Forecast")
                st.line_chart(df.set_index("time")["aqi"])
                st.subheader("Your Plan")
                plan = recommend(activities, df)
                st.dataframe(plan, hide_index=True, use_container_width=True)
                st.download_button("📥 Download", plan.to_csv(index=False), "plan.csv", "text/csv")
