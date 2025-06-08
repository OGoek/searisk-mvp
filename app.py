import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# Open-Meteo API (kostenfrei, keine Key notwendig)
OPEN_METEO_URL = "https://marine-api.open-meteo.com/v1/marine"

# User-Agent für Nominatim Geocoding (bitte E-Mail anpassen)
USER_AGENT = "SeaRiskAIApp/1.0 (ozan.goektas@gmail.com)"

# --- Funktionen ---

def geocode_place(place_name: str):
    """Ortname zu Koordinaten mit OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": place_name, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, params=params, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        if len(data) == 0:
            st.error(f"Ort '{place_name}' nicht gefunden.")
            return None, None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        return lat, lon
    except Exception as e:
        st.error(f"Geocoding Fehler: {e}")
        return None, None

def fetch_open_meteo_forecast(lat, lon, start_date, days=7):
    """Wetterdaten (Wellenhöhe, Wind) von Open-Meteo für maritimen Bereich."""
    start_iso = start_date.strftime("%Y-%m-%dT%H:%M")
    end_date = start_date + timedelta(days=days)
    end_iso = end_date.strftime("%Y-%m-%dT%H:%M")
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height,wind_speed_10m",
        "start": start_iso,
        "end": end_iso,
        "timezone": "UTC"
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
        hours = data.get("hourly", {}).get("time", [])
        waves = data.get("hourly", {}).get("wave_height", [])
        winds = data.get("hourly", {}).get("wind_speed_10m", [])
        if not (hours and waves and winds):
            st.warning("Keine vollständigen Wetterdaten erhalten.")
            return []
        forecast = []
        # Jeden 24. Stundenwert (tagesweise)
        for i in range(0, len(hours), 24):
            forecast.append({
                "time": hours[i],
                "wave": waves[i],
                "wind": winds[i],
            })
        return forecast
    except Exception as e:
        st.error(f"Open-Meteo API Fehler: {e}")
        return []

def compute_risk(wave, wind, vessel_type):
    """Einfaches Risikomodell basierend auf Wellenhöhe, Windgeschwindigkeit, Schiffstyp."""
    risk = 0
    # Beispielgewichtung
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

    # Unterschiedliche Schiffstypen (nur kommerzielle berücksichtigt)
    if vessel_type == "Panamax" or vessel_type == "Post-Panamax":
        risk += 5
    elif vessel_type == "Bulk Carrier":
        risk += 10
    elif vessel_type == "Container Ship":
        risk += 8
    elif vessel_type == "Tanker":
        risk += 12
    else:
        risk += 7  # Sonstige

    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

# --- Streamlit UI ---

st.title("🚢 SeaRisk AI MVP")

col1, col2 = st.columns(2)

with col1:
    origin_input = st.text_input("Start-Hafen (z.B. Hamburg)", value="Hamburg")
    destination_input = st.text_input("Ziel-Hafen (z.B. Rotterdam)", value="Rotterdam")
    vessel_type = st.selectbox("Schiffstyp", ["Container Ship", "Bulk Carrier", "Panamax", "Post-Panamax", "Tanker"])

with col2:
    start_date = st.date_input("Startdatum", datetime.utcnow().date())
    st.write("**Hinweis:** Die Prognose umfasst 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if origin_input.strip() == "" or destination_input.strip() == "":
        st.error("Bitte Start- und Zielhafen eingeben.")
    elif origin_input.strip().lower() == destination_input.strip().lower():
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        # Geocode Hafen
        origin_lat, origin_lon = geocode_place(origin_input)
        dest_lat, dest_lon = geocode_place(destination_input)

        if None in [origin_lat, origin_lon, dest_lat, dest_lon]:
            st.error("Koordinaten konnten nicht ermittelt werden.")
        else:
            st.subheader("📍 Hafenkoordinaten")
            st.write(f"{origin_input}: ({origin_lat:.4f}, {origin_lon:.4f})")
            st.write(f"{destination_input}: ({dest_lat:.4f}, {dest_lon:.4f})")

            # Wetterdaten abrufen
            forecast = fetch_open_meteo_forecast(origin_lat, origin_lon, datetime.combine(start_date, datetime.min.time()), days=7)

            if not forecast:
                st.error("Wetterdaten konnten nicht geladen werden.")
            else:
                # Risiko berechnen
                for day in forecast:
                    day["risk"] = compute_risk(day["wave"], day["wind"], vessel_type)

                df = pd.DataFrame(forecast)
                df["time"] = pd.to_datetime(df["time"]).dt.date

                st.subheader("📊 Risiko für die nächsten 7 Tage (Prognose)")
                st.dataframe(df.rename(columns={
                    "time": "Datum",
                    "wave": "Wellenhöhe (m)",
                    "wind": "Windgeschw. (m/s)",
                    "risk": "Risiko (0-100)"
                }))

                wave_trend = calculate_trend(df["wave"].values)
                wind_trend = calculate_trend(df["wind"].values)
                risk_trend = calculate_trend(df["risk"].values)

                st.write(f"Wellenhöhe Trend (Steigung pro Tag): {wave_trend:.3f} m/Tag")
                st.write(f"Windgeschwindigkeit Trend (Steigung pro Tag): {wind_trend:.3f} m/s/Tag")
                st.write(f"Risiko Trend (Steigung pro Tag): {risk_trend:.2f} Risiko-Punkte/Tag")

                # Diagramm
                fig, ax = plt.subplots(figsize=(10,4))
                ax.plot(df["Datum"], df["Wellenhöhe (m)"], label="Wellenhöhe (m)")
                ax.plot(df["Datum"], df["Windgeschw. (m/s)"], label="Windgeschwindigkeit (m/s)")
                ax.plot(df["Datum"], df["Risiko (0-100)"], label="Risiko")
                ax.legend()
                ax.set_xticklabels(df["Datum"], rotation=45, ha='right')
                ax.set_title("Prognose und Risikoentwicklung (7 Tage)")
                st.pyplot(fig)

            # Schifffahrtsroute als Wasserweg (vereinfacht, per Zwischenpunkte)
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

            st.subheader("🗺️ Geschätzte Schifffahrtsroute (vereinfacht)")
            st.pydeck_chart(pdk.Deck(layers=[route_layer], initial_view_state=view_state))
