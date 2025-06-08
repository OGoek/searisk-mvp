import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# API Keys
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006"
metno_headers = {
    "User-Agent": "(SeaRiskAIApp/1.0 ozan.goektas@gmail.com)"
}

# Beispiel-Portkoordinaten (Lat, Lon)
port_coords = {
    "Rotterdam": (51.95, 4.13),
    "Hamburg": (53.54, 9.98),
    "New York": (40.7128, -74.0060),
    "Singapur": (1.2644, 103.8406),
}

# Risikoberechnung
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

    if vessel_type in ["Fischkutter", "Fähre"]:
        risk += 10

    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

# API Abrufe
def get_stormglass_data(lat, lon, start_dt, end_dt, is_historical=False):
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
        for t in timeseries[:7*24:24]:  # je 24h ein Wert
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

# Streamlit UI
st.title("🚢 SeaRisk AI MVP")

col1, col2 = st.columns(2)

with col1:
    origin = st.selectbox("Start-Hafen wählen", list(port_coords.keys()))
    destination = st.selectbox("Ziel-Hafen wählen", list(port_coords.keys()))
    vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Fischkutter", "Fähre", "Tanker"])

with col2:
    start_date = st.date_input("Startdatum", datetime.utcnow().date())
    st.write("**Hinweis:** Die Prognose umfasst 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if origin == destination:
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        origin_lat, origin_lon = port_coords[origin]
        dest_lat, dest_lon = port_coords[destination]

        st.subheader("📍 Hafenkoordinaten")
        st.write(f"{origin}: ({origin_lat:.4f}, {origin_lon:.4f})")
        st.write(f"{destination}: ({dest_lat:.4f}, {dest_lon:.4f})")

        # Historische Daten (letzte 30 Tage bis heute)
        end_hist = datetime.utcnow()
        start_hist = end_hist - timedelta(days=30)
        hist_data = get_stormglass_data(origin_lat, origin_lon, start_hist, end_hist, is_historical=True)

        if not hist_data:
            st.warning("Keine historischen Daten verfügbar.")
        else:
            hist_risks = [compute_risk(d['wave'], d['wind'], vessel_type) for d in hist_data if d['wave'] is not None and d['wind'] is not None]
            avg_hist_risk = np.mean(hist_risks) if hist_risks else 0
            st.subheader("⚓ Generelles Risiko basierend auf historischen Daten (letzte 30 Tage)")
            st.write(f"📈 Durchschnittliches Risiko: **{avg_hist_risk:.1f} / 100**")

        # Prognose Daten (7 Tage ab Startdatum)
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

            wave_trend = calculate_trend(df["wave"].values)
            wind_trend = calculate_trend(df["wind"].values)
            risk_trend = calculate_trend(df["risk"].values)

            st.write(f"Wellenhöhe Trend (Steigung pro Tag): {wave_trend:.3f} m/Tag")
            st.write(f"Windgeschwindigkeit Trend (Steigung pro Tag): {wind_trend:.3f} m/s/Tag")
            st.write(f"Risiko Trend (Steigung pro Tag): {risk_trend:.2f} Risiko-Punkte/Tag")

            # Diagramm mit matplotlib
            fig, ax = plt.subplots(figsize=(10,4))
            ax.plot(df["time"], df["wave"], label="Wellenhöhe (m)")
            ax.plot(df["time"], df["wind"], label="Windgeschwindigkeit (m/s)")
            ax.plot(df["time"], df["risk"], label="Risiko")
            ax.legend()
            ax.set_xticks(range(len(df["time"])))
            ax.set_xticklabels(df["time"], rotation=45, ha='right')
            ax.set_title("Prognose und Risikoentwicklung (7 Tage)")
            st.pyplot(fig)

        # Beispielhafte Wasserweg-Route (hier z.B. Rotterdam → Dover → Atlantik → New York)
        route_coords = [
            [origin_lon, origin_lat],
            [1.8, 50.9],      # Ärmelkanal (Dover)
            [-10.0, 45.0],    # Mittlerer Atlantik
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

        st.subheader("🗺️ Geschätzte Schifffahrtsroute")
        st.pydeck_chart(pdk.Deck(layers=[route_layer], initial_view_state=view_state))
