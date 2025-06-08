import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# API Keys & Headers
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006"  # deinen Key hier einsetzen
metno_headers = {
    "User-Agent": "(SeaRiskAIApp/1.0 ozan.goektas@gmail.com)"
}

def compute_risk(wave, wind, vessel_type):
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

    # Kein Extra-Risiko für Fischkutter/Fähre mehr
    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

def get_stormglass_data(lat, lon, start_dt, end_dt):
    url = "https://api.stormglass.io/v2/weather/point"
    params = {
        'lat': lat,
        'lng': lon,
        'params': 'waveHeight,windSpeed',
        'start': int(start_dt.timestamp()),
        'end': int(end_dt.timestamp())
    }
    headers = {'Authorization': stormglass_api_key}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        result = []
        for hour in data.get("hours", []):
            wave = hour.get("waveHeight", {}).get("noaa", 0)
            wind = hour.get("windSpeed", {}).get("noaa", 0)
            time = hour.get("time", "")
            result.append({"time": time, "wave": wave, "wind": wind})
        return result
    except Exception as e:
        st.warning(f"⚠️ Stormglass API Fehler: {e}")
        return []

def get_metno_forecast(lat, lon):
    url = f"https://api.met.no/weatherapi/oceanforecast/2.0/complete?lat={lat}&lon={lon}"
    try:
        response = requests.get(url, headers=metno_headers)
        response.raise_for_status()
        timeseries = response.json().get("properties", {}).get("timeseries", [])
        forecast = []
        for t in timeseries[:7*24:24]:
            details = t["data"]["instant"]["details"]
            wave = details.get("significantWaveHeight", 0)
            wind = details.get("windSpeed", 0)
            forecast.append({
                "time": t["time"],
                "wave": wave,
                "wind": wind
            })
        return forecast
    except Exception as e:
        st.warning(f"⚠️ Met.no API Fehler: {e}")
        return []

st.title("🚢 SeaRisk AI MVP")

st.subheader("Hafen Koordinaten manuell eingeben")

col1, col2 = st.columns(2)
with col1:
    origin_lat = st.number_input("Start Hafen Latitude", value=51.95, format="%.5f")
    origin_lon = st.number_input("Start Hafen Longitude", value=4.13, format="%.5f")
with col2:
    dest_lat = st.number_input("Ziel Hafen Latitude", value=40.7128, format="%.5f")
    dest_lon = st.number_input("Ziel Hafen Longitude", value=-74.0060, format="%.5f")

vessel_type = st.selectbox("Schiffstyp auswählen", [
    "Containerschiff",
    "Bulker",
    "Panamax",
    "Kümo",
    "Tanker",
    "Supertanker"
])

start_date = st.date_input("Startdatum der Analyse", datetime.utcnow().date())
st.write("**Hinweis:** Die Prognose umfasst 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if (origin_lat == dest_lat) and (origin_lon == dest_lon):
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        st.subheader("📍 Eingabedaten")
        st.write(f"Start Hafen: ({origin_lat:.5f}, {origin_lon:.5f})")
        st.write(f"Ziel Hafen: ({dest_lat:.5f}, {dest_lon:.5f})")
        st.write(f"Schiffstyp: {vessel_type}")
        st.write(f"Startdatum: {start_date}")

        end_hist = datetime.utcnow()
        start_hist = end_hist - timedelta(days=30)
        hist_data = get_stormglass_data(origin_lat, origin_lon, start_hist, end_hist)

        if not hist_data:
            st.warning("Keine historischen Daten verfügbar.")
        else:
            hist_risks = [compute_risk(d['wave'], d['wind'], vessel_type) for d in hist_data if d['wave'] is not None and d['wind'] is not None]
            avg_hist_risk = np.mean(hist_risks) if hist_risks else 0
            st.subheader("⚓ Generelles Risiko basierend auf historischen Daten (letzte 30 Tage)")
            st.write(f"📈 Durchschnittliches Risiko: **{avg_hist_risk:.1f} / 100**")

        start_forecast = datetime.combine(start_date, datetime.min.time())
        end_forecast = start_forecast + timedelta(days=7)

        sg_forecast = get_stormglass_data(origin_lat, origin_lon, start_forecast, end_forecast)
        met_forecast = get_metno_forecast(origin_lat, origin_lon)

        if not sg_forecast or not met_forecast:
            st.error("Prognosedaten konnten nicht geladen werden.")
        else:
            length = min(len(sg_forecast), len(met_forecast))
            combined = []
            for i in range(length):
                avg_wave = (sg_forecast[i]["wave"] + met_forecast[i]["wave"]) / 2
                avg_wind = (sg_forecast[i]["wind"] + met_forecast[i]["wind"]) / 2
                risk = compute_risk(avg_wave, avg_wind, vessel_type)
                combined.append({
                    "time": sg_forecast[i]["time"][:10],
                    "wave": avg_wave,
                    "wind": avg_wind,
                    "risk": risk
                })

            df = pd.DataFrame(combined)

            st.subheader("📊 Risiko für die nächsten 7 Tage (Prognose)")
            st.dataframe(df.rename(columns={
                "time": "Datum",
                "wave": "Wellenhöhe (m)",
                "wind": "Windgeschw. (m/s)",
                "risk": "Risiko"
            }))

            wave_trend = calculate_trend(df["Wellenhöhe (m)"].values)
            wind_trend = calculate_trend(df["Windgeschw. (m/s)"].values)
            risk_trend = calculate_trend(df["Risiko"].values)

            st.write(f"Wellenhöhe Trend (Steigung pro Tag): {wave_trend:.3f} m/Tag")
            st.write(f"Windgeschwindigkeit Trend (Steigung pro Tag): {wind_trend:.3f} m/s/Tag")
            st.write(f"Risiko Trend (Steigung pro Tag): {risk_trend:.2f} Risiko-Punkte/Tag")

            fig, ax = plt.subplots(figsize=(10,4))
            ax.plot(df["Datum"], df["Wellenhöhe (m)"], label="Wellenhöhe (m)")
            ax.plot(df["Datum"], df["Windgeschw. (m/s)"], label="Windgeschwindigkeit (m/s)")
            ax.plot(df["Datum"], df["Risiko"], label="Risiko")
            ax.legend()
            ax.set_xticklabels(df["Datum"], rotation=45, ha='right')
            ax.set_title("Prognose und Risikoentwicklung (7 Tage)")
            st.pyplot(fig)

        route_coords = [
            [origin_lon, origin_lat],
            [dest_lon, dest_lat]
        ]

        route_layer = pdk.Layer(
            "PathLayer",
            data=[{"path": route_coords}],
            get_path="path",
            get_width=5,
            get_color=[0, 100, 255],
            width_min_pixels=3,
        )

        midpoint_lon = np.mean([pt[0] for pt in route_coords])
        midpoint_lat = np.mean([pt[1] for pt in route_coords])

        view_state = pdk.ViewState(
            longitude=midpoint_lon,
            latitude=midpoint_lat,
            zoom=3,
            pitch=0,
        )

        st.subheader("🗺️ Geschätzte Schifffahrtsroute (Luftlinie)")
        st.pydeck_chart(pdk.Deck(layers=[route_layer], initial_view_state=view_state))
