
import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# Schiffstypen mit Einflussfaktor
VESSEL_TYPES = {
    "Containerschiff": 1.0,
    "Panamax": 1.1,
    "Post-Panamax": 1.2,
    "Supramax": 1.3,
    "Aframax": 1.4,
    "Suezmax": 1.5,
    "VLCC": 1.6,
    "ULCC": 1.7
}

def geocode_location(place):
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={place}&format=json&limit=1"
        headers = {"User-Agent": "SeaRiskAIApp/1.0 (ozan.goektas@gmail.com)"}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return lat, lon
        return None, None
    except Exception as e:
        st.warning(f"Geocoding Fehler: {e}")
        return None, None

def fetch_open_meteo_forecast(lat, lon, start_date, days=7):
    try:
        end_date = start_date + timedelta(days=days)
        url = (
            "https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat}&longitude={lon}"
            "&hourly=wave_height"
            "&hourly=wind_speed_10m"
            f"&start={start_date.strftime('%Y-%m-%dT%H:%M')}"
            f"&end={end_date.strftime('%Y-%m-%dT%H:%M')}"
            "&timezone=UTC"
        )
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        times = data["hourly"]["time"]
        wave = data["hourly"]["wave_height"]
        wind = data["hourly"]["wind_speed_10m"]
        forecast = []
        for t, w, ws in zip(times, wave, wind):
            forecast.append({"time": t, "wave": w, "wind": ws})
        return forecast
    except Exception as e:
        st.warning(f"⚠️ Open-Meteo API Fehler: {e}")
        return []

def compute_risk(wave, wind, vessel_factor):
    risk = 0
    if wave > 4:
        risk += 40
    elif wave > 2:
        risk += 20
    else:
        risk += 5

    if wind > 15:
        risk += 40
    elif wind > 8:
        risk += 20
    else:
        risk += 5

    risk *= vessel_factor
    return min(int(risk), 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

st.title("🌊 SeaRisk AI – Maritime Risikoanalyse")

col1, col2 = st.columns(2)
with col1:
    origin = st.text_input("Start-Hafen", "Rotterdam")
    destination = st.text_input("Ziel-Hafen", "New York")
with col2:
    vessel_type = st.selectbox("Schiffstyp", list(VESSEL_TYPES.keys()))
    start_date = st.date_input("Startdatum", datetime.utcnow().date())

if st.button("Analyse starten"):
    origin_lat, origin_lon = geocode_location(origin)
    dest_lat, dest_lon = geocode_location(destination)

    if not origin_lat or not dest_lat:
        st.error("Konnte Start- oder Zielort nicht finden.")
    else:
        st.success(f"{origin}: ({origin_lat:.2f}, {origin_lon:.2f})")
        st.success(f"{destination}: ({dest_lat:.2f}, {dest_lon:.2f})")

        forecast = fetch_open_meteo_forecast(origin_lat, origin_lon, datetime.combine(start_date, datetime.min.time()), days=7)

        if not forecast:
            st.error("Keine Prognosedaten verfügbar.")
        else:
            vessel_factor = VESSEL_TYPES[vessel_type]
            df = pd.DataFrame(forecast)
            df["risk"] = df.apply(lambda row: compute_risk(row["wave"], row["wind"], vessel_factor), axis=1)
            df["time"] = pd.to_datetime(df["time"])
            daily = df.groupby(df["time"].dt.date).agg({
                "wave": "mean",
                "wind": "mean",
                "risk": "mean"
            }).reset_index()

            st.subheader("📊 Risikoanalyse (7 Tage)")
            st.dataframe(daily.rename(columns={"time": "Datum", "wave": "Wellenhöhe (m)", "wind": "Wind (m/s)", "risk": "Risiko"}))

            fig, ax = plt.subplots()
            ax.plot(daily["time"], daily["risk"], label="Risiko")
            ax.plot(daily["time"], daily["wave"], label="Wellenhöhe")
            ax.plot(daily["time"], daily["wind"], label="Windgeschwindigkeit")
            ax.set_title("7-Tage-Risikoentwicklung")
            ax.set_xlabel("Datum")
            ax.set_ylabel("Wert")
            ax.legend()
            plt.xticks(rotation=45)
            st.pyplot(fig)

            st.subheader("📍 Geschätzte Route")
            route = [
                [origin_lon, origin_lat],
                [dest_lon, dest_lat]
            ]
            layer = pdk.Layer(
                "PathLayer",
                data=[{"path": route}],
                get_path="path",
                get_width=4,
                get_color=[255, 0, 0]
            )
            view = pdk.ViewState(
                latitude=(origin_lat + dest_lat)/2,
                longitude=(origin_lon + dest_lon)/2,
                zoom=2
            )
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view))
