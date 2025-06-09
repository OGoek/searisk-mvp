import streamlit as st
import requests
import numpy as np
import folium
from streamlit_folium import folium_static
from geopy.distance import geodesic
from datetime import datetime, timedelta
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

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
CARGO_SECURITY_FACTORS = {
    "Standard": 1.0,
    "Verstärkt": 0.8,
    "Hoch": 0.6
}
KNOWN_PORTS = {
    "rotterdam": (51.9225, 4.47917),
    "new york": (40.7128, -74.0060),
    "istanbul": (41.0054, 28.9760)
}
ROUTE_WAYPOINTS = {
    ("rotterdam", "new york"): [
        (51.9225, 4.47917),
        (51.0, 2.0),
        (50.0, -5.0),
        (48.0, -20.0),
        (44.0, -40.0),
        (40.7128, -74.0060)
    ],
    ("rotterdam", "istanbul"): [
        (51.9225, 4.47917),
        (51.0, 2.0),
        (49.0, -2.0),
        (44.0, -8.0),
        (36.0, -5.0),
        (38.0, 5.0),
        (38.0, 15.0),
        (40.0, 26.0),
        (41.0054, 28.9760)
    ]
}

# Random-Forest-Modell für Risikoberechnung
@st.cache_resource
def load_risk_model():
    """Lädt und trainiert ein Random-Forest-Modell mit synthetischen Containerverlustdaten."""
    data = pd.DataFrame({
        "wave_height": [2, 4, 6, 1, 5, 3, 7, 2, 4, 8],
        "wind_speed": [10, 15, 20, 5, 18, 8, 25, 6, 12, 22],
        "ship_size": [50000, 80000, 60000, 40000, 70000, 50000, 90000, 45000, 65000, 80000],
        "cargo_security": [1.0, 0.8, 1.0, 0.6, 0.8, 1.0, 1.0, 0.6, 0.8, 1.0],
        "loss_occurred": [0, 1, 1, 0, 1, 0, 1, 0, 0, 1]
    })
    X = data[["wave_height", "wind_speed", "ship_size", "cargo_security"]]
    y = data["loss_occurred"]
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    return model

risk_model = load_risk_model()

# Geocoding-Funktion
@st.cache_data(ttl=86400)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def geocode_city(city_name):
    """Geocodiert einen Hafen mit vordefinierten Koordinaten oder Nominatim-API."""
    try:
        if city_name.lower() in KNOWN_PORTS:
            lat, lon = KNOWN_PORTS[city_name.lower()]
            st.write(f"Verwende vordefinierte Koordinaten für {city_name}: ({lat:.4f}, {lon:.4f})")
            return lat, lon
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
        st.error(f"Hafen {city_name} nicht gefunden.")
        return None
    except Exception as e:
        st.error(f"Geocoding-Fehler für {city_name}: {e}")
        return None

# Fallback-Routenpunkte
def generate_sea_waypoints(start_lat, start_lon, end_lat, end_lon, num_points=5):
    """Generiert vereinfachte Seewegpunkte zwischen Start und Ziel."""
    lats = np.linspace(start_lat, end_lat, num_points)
    lons = np.linspace(start_lon, end_lon, num_points)
    waypoints = list(zip(lats, lons))
    st.warning("Fallback-Route kann Landmassen kreuzen. Für präzise Seewege bitte vordefinierte Route verwenden.")
    return waypoints

# OpenSeaMap-Daten abrufen
@st.cache_data(ttl=3600)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def fetch_openseamap_data(min_lat, min_lon, max_lat, max_lon):
    """Ruft nautische Daten von OpenSeaMap ab und konvertiert sie in GeoJSON."""
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node["seamark:type"~"buoy_lateral|buoy_cardinal|lighthouse|harbour"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["seamark:type"~"harbour|dock"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """
        response = requests.post(overpass_url, data={"data": overpass_query}, timeout=API_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        geojson = {"type": "FeatureCollection", "features": []}
        for element in data.get("elements", []):
            if "tags" not in element or "seamark:type" not in element["tags"]:
                continue
            if element["type"] == "node":
                feature = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [element["lon"], element["lat"]]},
                    "properties": element.get("tags", {})
                }
                geojson["features"].append(feature)
            elif element["type"] == "way":
                coords = []
                for node_id in element.get("nodes", []):
                    for node in data["elements"]:
                        if node["type"] == "node" and node["id"] == node_id:
                            coords.append([node["lon"], node["lat"]])
                if coords:
                    feature = {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": element.get("tags", {})
                    }
                    geojson["features"].append(feature)
        if not geojson["features"]:
            st.warning("Keine gültigen OpenSeaMap-Daten gefunden.")
        return geojson
    except Exception as e:
        st.warning(f"Fehler beim Abrufen der OpenSeaMap-Daten: {e}")
        return {"type": "FeatureCollection", "features": []}

# Wetterdaten abrufen
@st.cache_data(ttl=3600)
@retry(stop=stop_after_attempt(3))
def fetch_marine_weather_data(lat, lon, start_date):
    """Ruft Wetterdaten (Wellenhöhe, Windgeschwindigkeit) von Open-Meteo ab."""
    try:
        start_iso = start_date.strftime("%Y-%m-%d")
        end_date = start_date + timedelta(days=FORECAST_DAYS)
        end_iso = end_date.strftime("%Y-%m-%d")
        marine_url = (
            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat}&longitude={lon}&hourly=wave_height"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        marine_response = requests.get(marine_url, timeout=API_TIMEOUT)
        marine_response.raise_for_status()
        marine_data = marine_response.json()
        if "hourly" not in marine_data or "wave_height" not in marine_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Marine API")
        
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&hourly=wind_speed_10m"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        weather_response = requests.get(weather_url, timeout=API_TIMEOUT)
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        if "hourly" not in weather_data or "wind_speed_10m" not in weather_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Wetter API")
        
        forecast = []
        for t, w, wi in zip(weather_data["hourly"]["time"], 
                          marine_data["hourly"]["wave_height"], 
                          weather_data["hourly"]["wind_speed_10m"]):
            if w is not None and wi is not None:
                forecast.append({"time": t, "wave_height": w, "wind_speed": wi})
        return forecast
    except Exception as e:
        st.warning(f"Fehler beim Abrufen der Wetterdaten für ({lat:.4f}, {lon:.4f}): {e}")
        return []

# Risikoberechnung mit KI
def compute_waypoint_risk(forecast, ship_type, cargo_security):
    """Berechnet das Risiko für einen Wegpunkt mit einem Random-Forest-Modell."""
    if not forecast:
        return None
    daily_data = {}
    for entry in forecast:
        date = entry["time"][:10]
        if date not in daily_data:
            daily_data[date] = {"wave_heights": [], "wind_speeds": []}
        daily_data[date]["wave_heights"].append(entry["wave_height"])
        daily_data[date]["wind_speeds"].append(entry["wind_speed"])
    
    daily_risks = []
    ship_factor = SHIP_TYPES[ship_type]
    cargo_factor = CARGO_SECURITY_FACTORS[cargo_security]
    for date, data in daily_data.items():
        max_wave = max(data["wave_heights"])
        max_wind = max(data["wind_speeds"])
        features = pd.DataFrame({
            "wave_height": [max_wave],
            "wind_speed": [max_wind],
            "ship_size": [50000],
            "cargo_security": [cargo_factor]
        })
        risk_prob = risk_model.predict_proba(features)[0][1] * 100
        adjusted_risk = min(risk_prob * (1.2 - ship_factor) * cargo_factor, 100)
        daily_risks.append({
            "date": date,
            "risk": int(adjusted_risk),
            "wave_height": max_wave,
            "wind_speed": max_wind,
            "reason": f"KI-Vorhersage (Wellen: {max_wave:.1f} m, Wind: {max_wind:.1f} m/s, Ladung: {cargo_security})"
        })
    return daily_risks

# Risikofarben
def get_risk_color(risk):
    """Bestimmt die Farbe basierend auf dem Risikowert."""
    if risk < 30:
        return 'green'
    elif risk < 60:
        return 'yellow'
    return 'red'

# Streamlit UI
st.title("🚢 SeaRisk AI – Risikoanalyse für Containerverluste")
col1, col2 = st.columns(2)
with col1:
    start_port = st.text_input("Start-Hafen (z. B. Rotterdam)", "Rotterdam")
    end_port = st.text_input("Ziel-Hafen (z. B. Istanbul)", "Istanbul")
with col2:
    ship_type = st.selectbox("Schiffstyp", list(SHIP_TYPES.keys()))
    cargo_security = st.selectbox("Ladungssicherung", list(CARGO_SECURITY_FACTORS.keys()))
    start_date = st.date_input("Startdatum", datetime.now().date())

if st.button("Risikoanalyse starten"):
    if start_port.lower() == end_port.lower():
        st.error("Start- und Ziel-Hafen müssen unterschiedlich sein.")
    else:
        with st.spinner("Berechne Seeweg-Risiko..."):
            start_coords = geocode_city(start_port)
            end_coords = geocode_city(end_port)
            if start_coords and end_coords:
                route_key = (start_port.lower(), end_port.lower())
                if route_key in ROUTE_WAYPOINTS:
                    waypoints = ROUTE_WAYPOINTS[route_key][1:-1]
                    all_points = [start_coords] + waypoints + [end_coords]
                else:
                    st.warning("Keine vordefinierte Route. Verwende vereinfachte Route.")
                    waypoints = generate_sea_waypoints(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
                    all_points = [start_coords] + waypoints + [end_coords]

                # Bounding Box
                lats = [p[0] for p in all_points]
                lons = [p[1] for p in all_points]
                min_lat, max_lat = min(lats) - 0.5, max(lats) + 0.5
                min_lon, max_lon = min(lons) - 0.5, max(lons) + 0.5

                # OpenSeaMap-Daten
                openseamap_geojson = fetch_openseamap_data(min_lat, min_lon, max_lat, max_lon)

                # Wetterdaten und Risiko
                progress_bar = st.progress(0)
                waypoint_risks = []
                daily_forecasts = []
                total_distance = 0
                distances = []
                for i in range(len(all_points) - 1):
                    dist = geodesic(all_points[i], all_points[i+1]).km
                    total_distance += dist
                    distances.append(dist)

                for i, wp in enumerate(all_points):
                    forecast = fetch_marine_weather_data(wp[0], wp[1], start_date)
                    daily_risks = compute_waypoint_risk(forecast, ship_type, cargo_security)
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
                    progress_bar.progress((i + 1) / len(all_points))

                if waypoint_risks and any(r > 0 for r in waypoint_risks):
                    weighted_risks = [r * d for r, d in zip(waypoint_risks[:-1], distances)]
                    total_risk = sum(weighted_risks) / total_distance if total_distance > 0 else 0
                    st.success(f"Gesamtrisiko für {start_port} → {end_port}: {total_risk:.2f}%")

                    # Karte
                    m = folium.Map(location=start_coords, zoom_start=4)
                    folium.Marker(start_coords, popup=f"Start: {start_port}", icon=folium.Icon(color='blue')).add_to(m)
                    for i, (wp, risk) in enumerate(zip(all_points[1:-1], waypoint_risks[1:-1]), 1):
                        color = get_risk_color(risk)
                        folium.CircleMarker(wp, radius=5, color=color, fill=True, popup=f"Wegpunkt {i}: Risiko {risk}%").add_to(m)
                    folium.Marker(end_coords, popup=f"Ziel: {end_port}", icon=folium.Icon(color='blue')).add_to(m)
                    folium.PolyLine(all_points, color='blue').add_to(m)

                    # OpenSeaMap-Layer
                    def style_function(feature):
                        properties = feature.get("properties", {})
                        seamark_type = properties.get("seamark:type", "unknown")
                        colors = {
                            "buoy_lateral": "purple",
                            "buoy_cardinal": "orange",
                            "lighthouse": "red",
                            "harbour": "green",
                            "dock": "blue"
                        }
                        return {"color": colors.get(seamark_type, "gray"), "weight": 3}

                    folium.GeoJson(
                        openseamap_geojson,
                        name="OpenSeaMap",
                        popup=folium.GeoJsonPopup(fields=["seamark:type", "seamark:name"], aliases=["Typ", "Name"]),
                        style_function=style_function,
                        show=True
                    ).add_to(m)
                    folium.LayerControl().add_to(m)
                    folium_static(m)
                    st.write("Nautische Daten: © OpenSeaMap, OpenStreetMap contributors")

                    # Reiseinformationen
                    speed_kmh = 37
                    travel_time_hours = total_distance / speed_kmh
                    st.write(f"Gesamtentfernung: {total_distance:.2f} km")
                    st.write(f"Geschätzte Reisezeit: {travel_time_hours:.2f} Stunden ({travel_time_hours/24:.1f} Tage)")

                    # Risikoprognose
                    st.subheader("Wetter- und Risikoprognose")
                    for wp_data in daily_forecasts:
                        st.write(f"Wegpunkt ({wp_data['lat']:.4f}, {wp_data['lon']:.4f})")
                        df = pd.DataFrame(wp_data["daily_risks"])
                        df = df[["date", "wave_height", "wind_speed", "risk", "reason"]]
                        df.columns = ["Datum", "Wellenhöhe (m)", "Windgesch oddly enough, the rest of the code is cut off here. Let me continue where it left off and complete the code cleanly.

<xaiArtifact artifact_id="f0ebff97-85e8-4116-87c1-b3d53f3ca442" artifact_version_id="b2fd0f07-d589-412b-b7c7-57e6b6123190" title="searisk_ai_mvp.py" contentType="text/python">
import streamlit as st
import requests
import numpy as np
import folium
from streamlit_folium import folium_static
from geopy.distance import geodesic
from datetime import datetime, timedelta
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

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
CARGO_SECURITY_FACTORS = {
    "Standard": 1.0,
    "Verstärkt": 0.8,
    "Hoch": 0.6
}
KNOWN_PORTS = {
    "rotterdam": (51.9225, 4.47917),
    "new york": (40.7128, -74.0060),
    "istanbul": (41.0054, 28.9760)
}
ROUTE_WAYPOINTS = {
    ("rotterdam", "new york"): [
        (51.9225, 4.47917),
        (51.0, 2.0),
        (50.0, -5.0),
        (48.0, -20.0),
        (44.0, -40.0),
        (40.7128, -74.0060)
    ],
    ("rotterdam", "istanbul"): [
        (51.9225, 4.47917),
        (51.0, 2.0),
        (49.0, -2.0),
        (44.0, -8.0),
        (36.0, -5.0),
        (38.0, 5.0),
        (38.0, 15.0),
        (40.0, 26.0),
        (41.0054, 28.9760)
    ]
}

# Random-Forest-Modell für Risikoberechnung
@st.cache_resource
def load_risk_model():
    """Lädt und trainiert ein Random-Forest-Modell mit synthetischen Containerverlustdaten."""
    data = pd.DataFrame({
        "wave_height": [2, 4, 6, 1, 5, 3, 7, 2, 4, 8],
        "wind_speed": [10, 15, 20, 5, 18, 8, 25, 6, 12, 22],
        "ship_size": [50000, 80000, 60000, 40000, 70000, 50000, 90000, 45000, 65000, 80000],
        "cargo_security": [1.0, 0.8, 1.0, 0.6, 0.8, 1.0, 1.0, 0.6, 0.8, 1.0],
        "loss_occurred": [0, 1, 1, 0, 1, 0, 1, 0, 0, 1]
    })
    X = data[["wave_height", "wind_speed", "ship_size", "cargo_security"]]
    y = data["loss_occurred"]
    X_train, _, y_train, _ = train_test_split(X, y, test_size=0.2, random_state=42)
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    return model

risk_model = load_risk_model()

# Geocoding-Funktion
@st.cache_data(ttl=86400)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def geocode_city(city_name):
    """Geocodiert einen Hafen mit vordefinierten Koordinaten oder Nominatim-API."""
    try:
        if city_name.lower() in KNOWN_PORTS:
            lat, lon = KNOWN_PORTS[city_name.lower()]
            st.write(f"Verwende vordefinierte Koordinaten für {city_name}: ({lat:.4f}, {lon:.4f})")
            return lat, lon
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
        st.error(f"Hafen {city_name} nicht gefunden.")
        return None
    except Exception as e:
        st.error(f"Geocoding-Fehler für {city_name}: {e}")
        return None

# Fallback-Routenpunkte
def generate_sea_waypoints(start_lat, start_lon, end_lat, end_lon, num_points=5):
    """Generiert vereinfachte Seewegpunkte zwischen Start und Ziel."""
    lats = np.linspace(start_lat, end_lat, num_points)
    lons = np.linspace(start_lon, end_lon, num_points)
    waypoints = list(zip(lats, lons))
    st.warning("Fallback-Route kann Landmassen kreuzen. Für präzise Seewege bitte vordefinierte Route verwenden.")
    return waypoints

# OpenSeaMap-Daten abrufen
@st.cache_data(ttl=3600)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def fetch_openseamap_data(min_lat, min_lon, max_lat, max_lon):
    """Ruft nautische Daten von OpenSeaMap ab und konvertiert sie in GeoJSON."""
    try:
        overpass_url = "https://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node["seamark:type"~"buoy_lateral|buoy_cardinal|lighthouse|harbour"]({min_lat},{min_lon},{max_lat},{max_lon});
          way["seamark:type"~"harbour|dock"]({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out geom;
        """
        response = requests.post(overpass_url, data={"data": overpass_query}, timeout=API_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        geojson = {"type": "FeatureCollection", "features": []}
        for element in data.get("elements", []):
            if "tags" not in element or "seamark:type" not in element["tags"]:
                continue
            if element["type"] == "node":
                feature = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [element["lon"], element["lat"]]},
                    "properties": element.get("tags", {})
                }
                geojson["features"].append(feature)
            elif element["type"] == "way":
                coords = []
                for node_id in element.get("nodes", []):
                    for node in data["elements"]:
                        if node["type"] == "node" and node["id"] == node_id:
                            coords.append([node["lon"], node["lat"]])
                if coords:
                    feature = {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": coords},
                        "properties": element.get("tags", {})
                    }
                    geojson["features"].append(feature)
        if not geojson["features"]:
            st.warning("Keine gültigen OpenSeaMap-Daten gefunden.")
        return geojson
    except Exception as e:
        st.warning(f"Fehler beim Abrufen der OpenSeaMap-Daten: {e}")
        return {"type": "FeatureCollection", "features": []}

# Wetterdaten abrufen
@st.cache_data(ttl=3600)
@retry(stop=stop_after_attempt(3))
def fetch_marine_weather_data(lat, lon, start_date):
    """Ruft Wetterdaten (Wellenhöhe, Windgeschwindigkeit) von Open-Meteo ab."""
    try:
        start_iso = start_date.strftime("%Y-%m-%d")
        end_date = start_date + timedelta(days=FORECAST_DAYS)
        end_iso = end_date.strftime("%Y-%m-%d")
        marine_url = (
            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat}&longitude={lon}&hourly=wave_height"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        marine_response = requests.get(marine_url, timeout=API_TIMEOUT)
        marine_response.raise_for_status()
        marine_data = marine_response.json()
        if "hourly" not in marine_data or "wave_height" not in marine_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Marine API")
        
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&hourly=wind_speed_10m"
            f"&start_date={start_iso}&end_date={end_iso}"
        )
        weather_response = requests.get(weather_url, timeout=API_TIMEOUT)
        weather_response.raise_for_status()
        weather_data = weather_response.json()
        if "hourly" not in weather_data or "wind_speed_10m" not in weather_data["hourly"]:
            raise ValueError("Unerwartetes API-Datenformat für Wetter API")
        
        forecast = []
        for t, w, wi in zip(weather_data["hourly"]["time"], 
                          marine_data["hourly"]["wave_height"], 
                          weather_data["hourly"]["wind_speed_10m"]):
            if w is not None and wi is not None:
                forecast.append({"time": t, "wave_height": w, "wind_speed": wi})
        return forecast
    except Exception as e:
        st.warning(f"Fehler beim Abrufen der Wetterdaten für ({lat:.4f}, {lon:.4f}): {e}")
        return []

# Risikoberechnung mit KI
def compute_waypoint_risk(forecast, ship_type, cargo_security):
    """Berechnet das Risiko für einen Wegpunkt mit einem Random-Forest-Modell."""
    if not forecast:
        return None
    daily_data = {}
    for entry in forecast:
        date = entry["time"][:10]
        if date not in daily_data:
            daily_data[date] = {"wave_heights": [], "wind_speeds": []}
        daily_data[date]["wave_heights"].append(entry["wave_height"])
        daily_data[date]["wind_speeds"].append(entry["wind_speed"])
    
    daily_risks = []
    ship_factor = SHIP_TYPES[ship_type]
    cargo_factor = CARGO_SECURITY_FACTORS[cargo_security]
    for date, data in daily_data.items():
        max_wave = max(data["wave_heights"])
        max_wind = max(data["wind_speeds"])
        features = pd.DataFrame({
            "wave_height": [max_wave],
            "wind_speed": [max_wind],
            "ship_size": [50000],
            "cargo_security": [cargo_factor]
        })
        risk_prob = risk_model.predict_proba(features)[0][1] * 100
        adjusted_risk = min(risk_prob * (1.2 - ship_factor) * cargo_factor, 100)
        daily_risks.append({
            "date": date,
 Dualität bleibt erhalten, und die App ist robust gegen API-Fehler.

### **Details der Bereinigung**
1. **Fehlerbehebung (OpenSeaMap)**:
   - **fetch_openseamap_data**: Filtert Elemente ohne `tags` oder `seamark:type`, um `KeyError` zu vermeiden.
   - **style_function**: Nutzt `feature.get("properties", {})` für sicheren Zugriff.
   - **Warnungen**: Klare Benutzerhinweise bei fehlenden Daten.

2. **Maschinelles Lernen**:
   - Random-Forest-Modell mit synthetischem Datensatz (Platzhalter, später durch echte Daten ersetzen).
   - `compute_waypoint_risk` integriert Schiffstyp und Ladungssicherung für die USP (Containerverlustrisiken).

3. **Code-Qualität**:
   - Einheitliche Einrückung (4 Leerzeichen).
   - Klare Funktionskommentare und Docstrings.
   - Entfernung redundanter Logik (z. B. konsolidierte Fehlerbehandlung).

4. **Streamlit-UI**:
   - Übersichtliche Spaltenaufteilung.
   - CSV-Export bleibt erhalten.

### **Ressourcenbedarf**
- **Kosten**: Keine zusätzlichen Kosten (Open-Source-Bibliotheken, Open-Meteo).
- **Zeit**: ~2–3 Stunden für Implementierung und Test.
- **Daten**: Synthetischer Datensatz muss durch echte Containerverlustdaten ersetzt werden (z. B. World Shipping Council, ~0–2.000 CHF).

### **Nächste Schritte**
1. **Speichern**: Speichere den Code in `app.py` und die `requirements.txt` im Projektverzeichnis.
2. **Installation**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # oder venv\Scripts\activate auf Windows
   pip install -r requirements.txt
   ```
3. **Testen**:
   ```bash
   streamlit run app.py
   ```
   Teste mit einer Route (z. B. Rotterdam–Istanbul) und überprüfe Karte, Risiko und CSV-Export.
4. **Cache leeren** (falls nötig):
   ```bash
   rm -rf ~/.streamlit/cache
   ```
5. **Daten**: Suche nach Containerverlustdaten (z. B. WSC-Berichte) und ersetze den Datensatz in `load_risk_model`.

Wenn der Fehler weiterhin auftritt oder du Hilfe beim Debugging (z. B. OpenSeaMap-Daten inspizieren) brauchst, teile mir die Ausgabe von `st.write("OpenSeaMap-Daten:", openseamap_geojson)` mit! Ich kann auch eine Upwork-Ausschreibung für einen Freelancer erstellen, falls du Unterstützung benötigst.
