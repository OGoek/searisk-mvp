import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# --- Geocoding via Nominatim OpenStreetMap ---
def geocode_place(place_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name,
        "format": "json",
        "limit": 1
    }
    try:
        response = requests.get(url, params=params, headers={"User-Agent": "SeaRiskAI/1.0"})
        response.raise_for_status()
        data = response.json()
        if len(data) == 0:
            return None, None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    except Exception as e:
        st.warning(f"⚠️ Geokodierung Fehler: {e}")
        return None, None

# --- Open-Meteo API für Wind und Wellen (7-Tage Vorhersage, stündlich) ---
def get_openmeteo_forecast(lat, lon, start_date):
    start_iso = start_date.strftime("%Y-%m-%d")  # Nur Datum, kein Zeitanteil
    end_date = start_date + timedelta(days=7)
    end_iso = end_date.strftime("%Y-%m-%d")      # Nur Datum

    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height,wind_speed_10m",
        "start": start_iso,
        "end": end_iso,
        "timezone": "UTC"
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        hours = data.get("hourly", {})
        times = hours.get("time", [])
        waves = hours.get("wave_height", [])
        winds = hours.get("wind_speed_10m", [])

        forecast = []
        # Wir nehmen jeweils Tageswerte (Mittelwert pro Tag)
        for day_idx in range(7):
            day_waves = waves[day_idx*24:(day_idx+1)*24]
            day_winds = winds[day_idx*24:(day_idx+1)*24]
            day_time = times[day_idx*24][:10]  # YYYY-MM-DD
            if len(day_waves) == 0 or len(day_winds) == 0:
                continue
            avg_wave = np.mean(day_waves)
            avg_wind = np.mean(day_winds)
            forecast.append({
                "time": day_time,
                "wave": avg_wave,
                "wind": avg_wind
            })
        return forecast
    except Exception as e:
        st.warning(f"⚠️ Open-Meteo API Fehler: {e}")
        return []

# --- Risikoberechnung mit Multiplikatoren ---
VESSEL_RISK_FACTORS = {
    "Containerschiff": 1.0,
    "Bulker": 1.1,
    "Panamax": 1.2,
    "Kümo": 1.3,
    "Tanker": 1.0,
    "Supertanker": 1.4
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

    multiplier = VESSEL_RISK_FACTORS.get(vessel_type, 1.0)
    risk *= multiplier
    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

st.title("🚢 SeaRisk AI MVP")

origin = st.text_input("Start-Hafen eingeben (z.B. Rotterdam)")
destination = st.text_input("Ziel-Hafen eingeben (z.B. New York)")

vessel_type = st.selectbox("Schiffstyp auswählen", list(VESSEL_RISK_FACTORS.keys()))

start_date = st.date_input("Startdatum der Analyse", datetime.utcnow().date())
st.write("**Hinweis:** Die Prognose umfasst 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if not origin or not destination:
        st.error("Bitte Start- und Zielhafen eingeben.")
    elif origin.lower() == destination.lower():
        st.error("Start- und Zielhafen dürfen nicht gleich sein.")
    else:
        origin_lat, origin_lon = geocode_place(origin)
        dest_lat, dest_lon = geocode_place(destination)

        if origin_lat is None or origin_lon is None:
            st.error(f"Start-Hafen '{origin}' konnte nicht geokodiert werden.")
        elif dest_lat is None or dest_lon is None:
            st.error(f"Ziel-Hafen '{destination}' konnte nicht geokodiert werden.")
        else:
            st.subheader("📍 Hafenkoordinaten")
            st.write(f"{origin}: ({origin_lat:.5f}, {origin_lon:.5f})")
            st.write(f"{destination}: ({dest_lat:.5f}, {dest_lon:.5f})")

            # Historische Daten: Open-Meteo liefert keine historischen Wellen/Wind
            # Wir verzichten hier auf historische Risikoanalyse (oder implementieren mit externer Quelle)

            # Prognose mit Open-Meteo API
            forecast = get_openmeteo_forecast(origin_lat, origin_lon, start_date)

            if not forecast:
                st.error("Prognosedaten konnten nicht geladen werden.")
            else:
                combined = []
                for entry in forecast:
                    risk = compute_risk(entry["wave"], entry["wind"], vessel_type)
                    combined.append({
                        "time": entry["time"],
                        "wave": entry["wave"],
                        "wind": entry["wind"],
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

            # Beispielhafter Wasserweg (noch einfache Luftlinie)
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
