import streamlit as st
import requests
import numpy as np
import folium
from streamlit_folium import folium_static
from geopy.distance import geodesic
from datetime import datetime, timedelta
import pandas as pd

# Konfiguration
st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# Konstanten
API_TIMEOUT = 10
FORECAST_DAYS = 7
SHIP_TYPES = {
    "Containerschiff": 1.0,
    "Tanker": 0.9,
    "Panamax": 0.8,
    "Supramax": 0.7,
    "Bulker": 0.85,
    "Feeder": 0.6
}

# Vordefinierte Koordinaten für bekannte Häfen
KNOWN_PORTS = {
    "rotterdam": (51.9225, 4.47917),    # Rotterdam, Niederlande
    "new york": (40.7128, -74.0060),    # New York City, USA
    "istanbul": (41.0054, 28.9760)      # Istanbul, Türkei (Hafen Haydarpaşa)
}

# Vordefinierte Seewegpunkte
ROUTE_WAYPOINTS = {
    ("rotterdam", "new york"): [
        (51.9225, 4.47917),   # Rotterdam
        (51.0, 2.0),          # Ärmelkanal (offshore)
        (50.0, -5.0),         # Atlantik vor UK
        (48.0, -20.0),        # Mittlerer Atlantik
        (44.0, -40.0),        # Atlantik
        (40.7128, -74.0060)   # New York
    ],
    ("rotterdam", "istanbul"): [
        (51.9225, 4.47917),   # Rotterdam
        (51.0, 2.0),          # Ärmelkanal (offshore)
        (49.0, -2.0),         # Atlantik vor Frankreich
        (44.0, -8.0),         # Biskaya (offshore)
        (36.0, -5.0),         # Straße von Gibraltar
        (38.0, 5.0),          # Mittelmeer (westlich)
        (38.0, 15.0),         # Mittelmeer (östlich)
        (40.0, 26.0),         # Dardanellen (offshore)
        (41.0054, 28.9760)    # Istanbul
    ]
}

# Geocoding-Funktion mit Caching
@st.cache_data(ttl=86400)  # Cache für 24 Stunden
def geocode_city(city_name):
    try:
        # Verwende vordefinierte Koordinaten, wenn verfügbar
        if city_name.lower() in KNOWN_PORTS:
            lat, lon = KNOWN_PORTS[city_name.lower()]
            st.write(f"Verwende vordefinierte Koordinaten für {city_name}: ({lat:.4f}, {lon:.4f})")
            return lat, lon

        # Nominatim-Suche für andere Häfen
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{city_name}, port", "format": "json", "limit": 1},
            headers={"User-Agent": "SeaRiskAIApp/1.0"},
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        results = response.json()
        if results:
            lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
            st.write(f"Geocodierte Koordinaten für {city_name}: ({lat:.4f}, {lon:.4f})")
            return lat, lon
        else:
            st.error(f"Hafen {city_name} nicht gefunden.")
            return None
    except Exception as e:
        st.error(f"Geocoding-Fehler für {city_name}: {e}")
        return None

# Seewegpunkte generieren (Fallback für nicht vordefinierte Routen)
def generate_sea_waypoints(start_lat, start_lon, end_lat, end_lon, num_points=5):
    lats = np.linspace(start_lat, end_lat, num_points)
    lons = np.linspace(start_lon, end_lon, num_points)
    waypoints = list(zip(lats, lons))
    st.warning("Fallback-Route kann Landmassen kreuzen. Für präzise Seewege bitte vordefinierte Route verwenden.")
    return waypoints

# Wetterdaten abrufen
@st.cache_data(ttl=3600)  # Cache für 1 Stunde
def fetch_weather_data(lat, lon, start_date):
    try:
        start_iso = start_date.strftime("%Y-%m-%d")
        end_date = start_date + timedelta(days=FORECAST_DAYS)
        end_iso = end_date.strftime("%Y-%m-%d")

        # Marine API für Wellenhöhe
        marine_url = (
            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wave_height"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        marine_response = requests.get(marine_url, timeout=API_TIMEOUT)
        marine_response.raise_for_status()
        marine_data = marine_response.json()

        if "hourly" not in marine_data or "wave_height" not in marine_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Marine API")

        wave_heights = marine_data["hourly"]["wave_height"]

        # Weather API für Windgeschwindigkeit
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wind_speed_10m"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        weather_response = requests.get(weather_url, timeout=API_TIMEOUT)
        weather_response.raise_for_status()
        weather_data = weather_response.json()

        if "hourly" not in weather_data or "wind_speed_10m" not in weather_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Weather API")

        wind_speeds = weather_data["hourly"]["wind_speed_10m"]
        times = weather_data["hourly"]["time"]

        forecast = []
        for t, w, wi in zip(times, wave_heights, wind_speeds):
            if w is not None and wi is not None:
                forecast.append({"time": t, "wave_height": w, "wind_speed": wi})
        return forecast
    except Exception as e:
        st.warning(f"Fehler beim Abrufen der Wetterdaten für ({lat:.4f}, {lon:.4f}): {e}")
        return []

# Risiko für einen Wegpunkt berechnen
def compute_waypoint_risk(forecast, ship_type):
    if not forecast:
        return None

    daily_data = {}
    for entry in forecast:
        date = entry["time"][:10]  # YYYY-MM-DD
        if date not in daily_data:
            daily_data[date] = {"wave_heights": [], "wind_speeds": []}
        daily_data[date]["wave_heights"].append(entry["wave_height"])
        daily_data[date]["wind_speeds"].append(entry["wind_speed"])

    daily_risks = []
    for date, data in daily_data.items():
        max_wave = max(data["wave_heights"])
        max_wind = max(data["wind_speeds"])
        base_risk = 0
        if max_wave > 4:
            base_risk += 40
        elif max_wave > 2:
            base_risk += 20
        else:
            base_risk += 5

        if max_wind > 15:
            base_risk += 40
        elif max_wind > 8:
            base_risk += 20
        else:
            base_risk += 5

        ship_factor = SHIP_TYPES[ship_type]
        risk = min(int(base_risk * (1.2 - ship_factor)), 100)
        daily_risks.append({"date": date, "risk": risk, "wave_height": max_wave, "wind_speed": max_wind})

    return daily_risks

# Farbe basierend auf Risiko
def get_risk_color(risk):
    if risk < 30:
        return 'green'
    elif risk < 60:
        return 'yellow'
    else:
        return 'red'

# Streamlit UI
st.title("🚢 SeaRisk AI – Risikoanalyse")

col1, col2 = st.columns(2)
with col1:
    start_port = st.text_input("Start-Hafen eingeben (z. B. Rotterdam)", "Rotterdam")
    end_port = st.text_input("Ziel-Hafen eingeben (z. B. Istanbul)", "Istanbul")
with col2:
    ship_type = st.selectbox("Schiffstyp", list(SHIP_TYPES.keys()))
    start_date = st.date_input("Startdatum", datetime.now().date())

if st.button("Risikoanalyse starten"):
    if start_port.lower() == end_port.lower():
        st.error("Start- und Ziel-Hafen müssen unterschiedlich sein.")
    else:
        with st.spinner("Berechne Seeweg-Risiko..."):
            start_coords = geocode_city(start_port)
            end_coords = geocode_city(end_port)
            if start_coords and end_coords:
                # Prüfen, ob vordefinierte Route verfügbar ist
                route_key = (start_port.lower(), end_port.lower())
                if route_key in ROUTE_WAYPOINTS:
                    waypoints = ROUTE_WAYPOINTS[route_key][1:-1]  # Ohne Start- und Zielpunkt
                    all_points = [start_coords] + waypoints + [end_coords]
                else:
                    st.warning("Keine vordefinierte Seeweg-Route verfügbar. Verwende vereinfachte Route.")
                    waypoints = generate_sea_waypoints(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
                    all_points = [start_coords] + waypoints + [end_coords]

                waypoint_risks = []
                daily_forecasts = []
                for wp in all_points:
                    forecast = fetch_weather_data(wp[0], wp[1], start_date)
                    daily_risks = compute_waypoint_risk(forecast, ship_type)
                    if daily_risks:
                        max_risk = max([dr["risk"] for dr in daily_risks])
                        waypoint_risks.append(max_risk)
                        daily_forecasts.append({
                            "lat": wp[0],
                            "lon": wp[1],
                            "daily_risks": daily_risks
                        })
                    else:
                        st.warning(f"Keine Wetterdaten für Wegpunkt ({wp[0]:.4f}, {wp[1]:.4f})")
                        waypoint_risks.append(0)

                if waypoint_risks and any(r > 0 for r in waypoint_risks):
                    total_risk = np.mean([r for r in waypoint_risks if r > 0])
                    st.success(f"Gesamtrisiko für die Seeweg-Route {start_port} → {end_port}: {total_risk:.2f}%")

                    # Karte erstellen
                    m = folium.Map(location=start_coords, zoom_start=4)
                    folium.Marker(start_coords, popup=f"Start: {start_port}", icon=folium.Icon(color='blue')).add_to(m)
                    for i, (wp, risk) in enumerate(zip(all_points[1:-1], waypoint_risks[1:-1]), 1):
                        color = get_risk_color(risk)
                        folium.CircleMarker(wp, radius=5, color=color, fill=True, popup=f"Wegpunkt {i}: Risiko {risk}%").add_to(m)
                    folium.Marker(end_coords, popup=f"Ziel: {end_port}", icon=folium.Icon(color='blue')).add_to(m)
                    folium.PolyLine(all_points, color='blue').add_to(m)
                    folium_static(m)

                    # Entfernung und Reisezeit berechnen
                    total_distance = 0
                    for i in range(len(all_points) - 1):
                        total_distance += geodesic(all_points[i], all_points[i+1]).km
                    speed_kmh = 37  # 20 knots ≈ 37 km/h
                    travel_time_hours = total_distance / speed_kmh
                    st.write(f"Gesamtentfernung (Seeweg): {total_distance:.2f} km")
                    st.write(f"Geschätzte Reisezeit: {travel_time_hours:.2f} Stunden ({travel_time_hours/24:.1f} Tage)")

                    # Aktuelle und 7-Tage-Prognose
                    st.subheader("Wetter- und Risikoprognose")
                    for wp_data in daily_forecasts:
                        st.write(f"Wegpunkt ({wp_data['lat']:.4f}, {wp_data['lon']:.4f})")
                        df = pd.DataFrame(wp_data["daily_risks"])
                        df = df[["date", "wave_height", "wind_speed", "risk"]]
                        df.columns = ["Datum", "Wellenhöhe (m)", "Windgeschw. (m/s)", "Risiko (%)"]
                        st.dataframe(df, use_container_width=True)
                else:
                    st.error("Keine ausreichenden Wetterdaten für die Risikoberechnung.")
