import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pydeck as pdk
import matplotlib.pyplot as plt

st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# API Keys & Header
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006-52eefa98-4468-11f0-b16b-0242ac130006"
metno_headers = {
    "User-Agent": "(SeaRiskAIApp/1.0 ozan.goektas@gmail.com)"
}

# Risiko-Berechnung basierend auf Wellen, Wind und Schiffstyp (hier nur kommerzielle Typen)
def compute_risk(wave, wind, vessel_type):
    risk = 0
    # Wellenhöhe-Risiko
    if wave > 4:
        risk += 40
    elif wave > 2:
        risk += 20
    else:
        risk += 5

    # Windgeschwindigkeit-Risiko
    if wind > 15:
        risk += 40
    elif wind > 8:
        risk += 20
    else:
        risk += 5

    # Schiffstyp-spezifisches Risiko
    if vessel_type in ["Panamax", "Bulk Carrier", "Containerschiff", "Tanker"]:
        risk += 10

    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

# Stormglass API (historische Daten)
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

# Met.no API (7-Tage-Prognose)
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

# Open-Meteo Marine API (7-Tage-Prognose), separate Anfragen für wave_height und wind_speed_10m
def get_openmeteo_forecast(lat, lon, start_date):
    start_iso = start_date.strftime("%Y-%m-%d")
    end_date = (start_date + timedelta(days=7)).strftime("%Y-%m-%d")

    base_url = "https://marine-api.open-meteo.com/v1/marine"
    
    # Wellenhöhe
    params_wave = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height",
        "start": start_iso,
        "end": end_date,
        "timezone": "UTC"
    }
    try:
        response_wave = requests.get(base_url, params=params_wave)
        response_wave.raise_for_status()
        data_wave = response_wave.json()
    except Exception as e:
        st.warning(f"⚠️ Open-Meteo Wellen API Fehler: {e}")
        return []

    # Windgeschwindigkeit
    params_wind = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wind_speed_10m",
        "start": start_iso,
        "end": end_date,
        "timezone": "UTC"
    }
    try:
        response_wind = requests.get(base_url, params=params_wind)
        response_wind.raise_for_status()
        data_wind = response_wind.json()
    except Exception as e:
        st.warning(f"⚠️ Open-Meteo Wind API Fehler: {e}")
        return []

    times = data_wave.get('hourly', {}).get('time', [])
    wave_heights = data_wave.get('hourly', {}).get('wave_height', [])
    wind_speeds = data_wind.get('hourly', {}).get('wind_speed_10m', [])

    forecast = []
    for t, wv, ws in zip(times, wave_heights, wind_speeds):
        forecast.append({
            "time": t,
            "wave": wv,
            "wind": ws
        })
    return forecast

# Geocoding über OpenStreetMap Nominatim (um Hafen manuell in Koordinaten umzuwandeln)
def geocode_place(place_name):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": place_name,
        "format": "json",
        "limit": 1
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            return lat, lon
        else:
            st.error(f"Ort '{place_name}' nicht gefunden.")
            return None, None
    except Exception as e:
        st.error(f"Geocoding Fehler: {e}")
        return None, None

# Streamlit UI
st.title("🚢 SeaRisk AI MVP")

col1, col2 = st.columns(2)

with col1:
    origin_input = st.text_input("Start-Hafen (z.B. Rotterdam, New York)")
    destination_input = st.text_input("Ziel-Hafen (z.B. Singapur, Hamburg)")
    vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Panamax", "Bulk Carrier", "Tanker"])

with col2:
    start_date = st.date_input("Startdatum", datetime.utcnow().date())
    st.write("**Hinweis:** Die Prognose umfasst 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if not origin_input or not destination_input:
        st.error("Bitte Start- und Ziel-Hafen eingeben.")
    elif origin_input.strip().lower() == destination_input.strip().lower():
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        origin_lat, origin_lon = geocode_place(origin_input)
        dest_lat, dest_lon = geocode_place(destination_input)

        if origin_lat is None or dest_lat is None:
            st.stop()

        st.subheader("📍 Hafenkoordinaten")
        st.write(f"{origin_input}: ({origin_lat:.4f}, {origin_lon:.4f})")
        st.write(f"{destination_input}: ({dest_lat:.4f}, {dest_lon:.4f})")

        # Historische Daten (Stormglass, letzte 30 Tage)
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

        # Prognose mit Open-Meteo (7 Tage ab Startdatum)
        forecast_data = get_openmeteo_forecast(origin_lat, origin_lon, start_date)

        if not forecast_data:
            st.error("Prognosedaten konnten nicht geladen werden.")
        else:
            # Risiko berechnen
            combined = []
            for entry in forecast_data:
                risk = compute_risk(entry["wave"], entry["wind"], vessel_type)
                combined.append({
                    "time": entry["time"][:10],
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

            wave_trend = calculate_trend(df["wave"].values)
            wind_trend = calculate_trend(df["wind"].values)
            risk_trend = calculate_trend(df["risk"].values)

            st.write(f"Wellenhöhe Trend: {wave_trend:+.3f} m/Tag")
            st.write(f"Windgeschwindigkeit Trend: {wind_trend:+.3f} m/s/Tag")
            st.write(f"Risiko Trend: {risk_trend:+.3f} Punkte/Tag")

            # Visualisierung der Risikoentwicklung
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(pd.to_datetime(df["time"]), df["risk"], marker="o", linestyle="-", color="red")
            ax.set_title("Risikoentwicklung in den nächsten 7 Tagen")
            ax.set_xlabel("Datum")
            ax.set_ylabel("Risiko (0-100)")
            ax.grid(True)
            st.pyplot(fig)

        # Karte mit Start- und Zielhafen
        midpoint = [(origin_lat + dest_lat) / 2, (origin_lon + dest_lon) / 2]
        route = pd.DataFrame({
            'lat': [origin_lat, dest_lat],
            'lon': [origin_lon, dest_lon]
        })

        st.subheader("🗺️ Schifffahrtsroute (gerade Linie)")
        st.map(route.rename(columns={"lat": "latitude", "lon": "longitude"}))

st.markdown("---")
st.caption("© 2025 SeaRisk AI MVP")
