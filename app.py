import streamlit as st
import requests
import numpy as np
from datetime import datetime, timedelta

# Konfiguration
st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# Hartcodierte Koordinaten für Häfen
HARBOUR_COORDS = {
    "Rotterdam": (51.9225, 4.47917),
    "New York": (40.7128, -74.0060),
}

# Funktion zum Abrufen von Wetterdaten
def fetch_weather_data(lat: float, lon: float, start_date: datetime) -> list[dict]:
    start_iso = start_date.strftime("%Y-%m-%d")
    end_date = start_date + timedelta(days=7)
    end_iso = end_date.strftime("%Y-%m-%d")

    marine_url = (
        f"https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=wave_height"
        f"&start_date={start_iso}&end_date={end_iso}"
    )
    marine_response = requests.get(marine_url)
    marine_data = marine_response.json()
    if "hourly" not in marine_data or "wave_height" not in marine_data["hourly"]:
        st.error(f"Fehler bei Marine API für ({lat}, {lon}): {marine_data}")
        return []
    wave_heights = marine_data["hourly"]["wave_height"]

    weather_url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=wind_speed_10m"
        f"&start_date={start_iso}&end_date={end_iso}"
    )
    weather_response = requests.get(weather_url)
    weather_data = weather_response.json()
    if "hourly" not in weather_data or "wind_speed_10m" not in weather_data["hourly"]:
        st.error(f"Fehler bei Weather API für ({lat}, {lon}): {weather_data}")
        return []
    wind_speeds = weather_data["hourly"]["wind_speed_10m"]
    times = weather_data["hourly"]["time"]

    forecast = []
    for t, w, wi in zip(times, wave_heights, wind_speeds):
        if w is not None and wi is not None:
            forecast.append({"time": t, "wave_height": w, "wind_speed": wi})
    return forecast

# Funktion zur Risikoberechnung
def compute_risk(wave_height: float, wind_speed: float, ship_factor: float = 1.0) -> int:
    base_risk = 0
    if wave_height > 4:
        base_risk += 40
    elif wave_height > 2:
        base_risk += 20
    else:
        base_risk += 5

    if wind_speed > 15:
        base_risk += 40
    elif wind_speed > 8:
        base_risk += 20
    else:
        base_risk += 5

    return min(int(base_risk * (1.2 - ship_factor)), 100)

# Wegpunkte entlang der Route generieren
def generate_waypoints(start_lat, start_lon, end_lat, end_lon, num_points=5):
    lats = np.linspace(start_lat, end_lat, num_points)
    lons = np.linspace(start_lon, end_lon, num_points)
    return list(zip(lats, lons))

# Hauptlogik
def calculate_route_risk(start_city: str, end_city: str, start_date: datetime):
    if start_city not in HARBOUR_COORDS or end_city not in HARBOUR_COORDS:
        st.error("Ungültiger Hafen.")
        return

    start_lat, start_lon = HARBOUR_COORDS[start_city]
    end_lat, end_lon = HARBOUR_COORDS[end_city]

    waypoints = generate_waypoints(start_lat, start_lon, end_lat, end_lon)
    route_risks = []

    for wp_lat, wp_lon in waypoints:
        forecast = fetch_weather_data(wp_lat, wp_lon, start_date)
        if forecast:
            risks = [compute_risk(entry["wave_height"], entry["wind_speed"]) for entry in forecast]
            avg_risk = np.mean(risks)
            route_risks.append(avg_risk)
            st.write(f"Wegpunkt ({wp_lat:.4f}, {wp_lon:.4f}): Risiko = {avg_risk:.2f}%")
        else:
            st.write(f"Keine Daten für Wegpunkt ({wp_lat:.4f}, {wp_lon:.4f})")

    if route_risks:
        total_risk = np.mean(route_risks)
        st.success(f"Gesamtrisiko für die Route {start_city} → {end_city}: {total_risk:.2f}%")
    else:
        st.error("Keine ausreichenden Daten für die Risikoberechnung.")

# Streamlit UI
st.title("🚢 SeaRisk AI – Risikoanalyse")

col1, col2 = st.columns(2)
with col1:
    start_city = st.selectbox("Starthafen", list(HARBOUR_COORDS.keys()))
    end_city = st.selectbox("Zielhafen", list(HARBOUR_COORDS.keys()))
with col2:
    start_date = st.date_input("Startdatum", datetime.utcnow().date())

if st.button("Risikoanalyse starten"):
    if start_city == end_city:
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        with st.spinner("Berechne Risiko..."):
            calculate_route_risk(start_city, end_city, datetime.combine(start_date, datetime.min.time()))
