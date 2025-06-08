import streamlit as st
import requests
from datetime import datetime, timedelta
from geopy.geocoders import Nominatim

st.set_page_config(page_title="SeaRisk AI", layout="centered")

# -----------------------------
# Geocoding-Funktion
# -----------------------------
def geocode_location(location):
    try:
        geolocator = Nominatim(user_agent="searisk_ai")
        loc = geolocator.geocode(location)
        if loc:
            return loc.latitude, loc.longitude
        else:
            return None, None
    except Exception as e:
        st.warning(f"🌍 Geocoding Fehler: {e}")
        return None, None

# -----------------------------
# Wetterdaten von Open-Meteo holen
# -----------------------------
def fetch_open_meteo_forecast(lat, lon, start_date, days=7):
    start_iso = start_date.strftime("%Y-%m-%dT%H:%M")
    end_date = start_date + timedelta(days=days)
    end_iso = end_date.strftime("%Y-%m-%dT%H:%M")

    params_wave = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height",
        "start": start_iso,
        "end": end_iso,
        "timezone": "UTC"
    }

    params_wind = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m",
        "start": start_iso,
        "end": end_iso,
        "timezone": "UTC"
    }

    try:
        resp_wave = requests.get("https://marine-api.open-meteo.com/v1/marine", params=params_wave)
        resp_wave.raise_for_status()
        wave_data = resp_wave.json()

        resp_wind = requests.get("https://marine-api.open-meteo.com/v1/marine", params=params_wind)
        resp_wind.raise_for_status()
        wind_data = resp_wind.json()

        times = wave_data.get("hourly", {}).get("time", [])
        waves = wave_data.get("hourly", {}).get("wave_height", [])
        winds = wind_data.get("hourly", {}).get("wind_speed_10m", [])

        result = []
        for i in range(len(times)):
            result.append({
                "time": times[i],
                "wave": waves[i] if i < len(waves) else None,
                "wind": winds[i] if i < len(winds) else None
            })

        return result

    except Exception as e:
        st.warning(f"⚠️ Open-Meteo API Fehler: {e}")
        return []

# -----------------------------
# Risiko-Logik (einfach)
# -----------------------------
def calculate_risk(forecast, vessel_type):
    risks = []
    for point in forecast:
        wave = point["wave"]
        wind = point["wind"]

        # Grundlogik: größere Schiffe (z. B. Panamax) = robuster
        wave_risk = wave if wave else 0
        wind_risk = wind if wind else 0

        # Risikofaktor nach Schiffstyp
        if vessel_type == "Containerschiff":
            factor = 1.0
        elif vessel_type == "Panamax":
            factor = 0.8
        elif vessel_type == "Supertanker":
            factor = 0.7
        elif vessel_type == "Bulker":
            factor = 0.9
        else:
            factor = 1.0

        combined = (wave_risk * 0.6 + wind_risk * 0.4) * factor
        risks.append(round(combined, 2))

    return risks

# -----------------------------
# UI
# -----------------------------
st.title("🌊 SeaRisk AI – Maritime Risikoanalyse")

col1, col2 = st.columns(2)
with col1:
    origin_input = st.text_input("🛳️ Start-Hafen", "Hamburg")
with col2:
    dest_input = st.text_input("⚓ Ziel-Hafen", "New York")

vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Panamax", "Supertanker", "Bulker"])

start_date = st.date_input("Startdatum der Route", datetime.today())

if st.button("📊 Risiko berechnen"):
    with st.spinner("Daten werden geladen..."):
        origin_lat, origin_lon = geocode_location(origin_input)
        dest_lat, dest_lon = geocode_location(dest_input)

        if None in (origin_lat, origin_lon, dest_lat, dest_lon):
            st.error("❌ Hafenkoordinaten konnten nicht bestimmt werden.")
        else:
            forecast = fetch_open_meteo_forecast(origin_lat, origin_lon, datetime.combine(start_date, datetime.min.time()), days=7)
            if not forecast:
                st.error("❌ Keine Wetterdaten verfügbar.")
            else:
                risks = calculate_risk(forecast, vessel_type)
                st.success("✅ Risikoanalyse abgeschlossen")

                # Visualisierung
                times = [entry["time"] for entry in forecast]
                st.line_chart({"Risikoindex": risks}, x=times)
                st.markdown("**Hinweis**: Ein höherer Risikoindex bedeutet potenziell gefährlichere Bedingungen für das ausgewählte Schiff.")

