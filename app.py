import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# Konfiguration
st.set_page_config(page_title="SeaRisk AI MVP", layout="wide")

# Konstanten
VESSEL_TYPES = {
    "Containerschiff": 1.0,
    "Tanker": 0.9,
    "Panamax": 0.8,
    "Supramax": 0.7,
    "Bulker": 0.85,
    "Feeder": 0.6
}
API_TIMEOUT = 10
FORECAST_DAYS = 7
OPEN_METEO_URL = "https://marine-api.open-meteo.com/v1/marine"
GEOCODING_URL = "https://nominatim.openstreetmap.org/search"

# Funktion zum Risikoberechnen
def compute_risk(wave_height: float, wind_speed: float, ship_factor: float) -> int:
    """Berechnet das Risiko basierend auf Wellenhöhe, Windgeschwindigkeit und Schiffstyp."""
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

# Geocoding-Funktion mit Caching
@st.cache_data(ttl=86400)  # Cache für 24 Stunden
def geocode_city(city_name: str) -> tuple[float, float] | None:
    """Konvertiert einen Stadtnamen in geografische Koordinaten (Breite, Länge)."""
    if not city_name.strip():
        st.error("Bitte geben Sie einen gültigen Stadtnamen ein.")
        return None

    try:
        response = requests.get(
            GEOCODING_URL,
            params={"q": city_name, "format": "json", "limit": 1},
            headers={"User-Agent": "SeaRiskAIApp/1.0"},
            timeout=API_TIMEOUT
        )
        response.raise_for_status()
        results = response.json()
        if not results:
            st.error(f"Keine Koordinaten für '{city_name}' gefunden.")
            return None
        return float(results[0]["lat"]), float(results[0]["lon"])
    except requests.RequestException as e:
        st.error(f"Geocoding-Fehler für '{city_name}': {e}")
        return None

# Wetterdaten abrufen mit Caching
@st.cache_data(ttl=3600)  # Cache für 1 Stunde
def fetch_open_meteo_forecast(lat: float, lon: float, start_date: datetime) -> list[dict]:
    """Ruft Wettervorhersagedaten von Open-Meteo ab."""
    try:
        start_iso = start_date.strftime("%Y-%m-%dT00:00")
        end_date = start_date + timedelta(days=FORECAST_DAYS)
        end_iso = end_date.strftime("%Y-%m-%dT00:00")

        url = (
            f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
            f"&hourly=wave_height,wind_speed_10m"
            f"&start={start_iso}&end={end_iso}&timezone=UTC"
        )
        response = requests.get(url, timeout=API_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        if "hourly" not in data or not all(
            key in data["hourly"] for key in ["time", "wave_height", "wind_speed_10m"]
        ):
            raise ValueError("Unerwartetes API-Datenformat")

        forecast = []
        for time, wave, wind in zip(
            data["hourly"]["time"],
            data["hourly"]["wave_height"],
            data["hourly"]["wind_speed_10m"]
        ):
            if wave is None or wind is None:
                continue
            forecast.append({
                "time": pd.to_datetime(time),
                "wave_height": wave,
                "wind_speed": wind
            })
        return forecast
    except (requests.RequestException, ValueError) as e:
        st.warning(f"Fehler beim Abrufen der Wetterdaten: {e}")
        return []

# Streamlit UI
st.title("🚢 SeaRisk AI – Risikoanalyse")

# Eingabefelder
col1, col2 = st.columns(2)
with col1:
    origin_city = st.text_input("Starthafen eingeben (z. B. Rotterdam)", key="origin")
    dest_city = st.text_input("Zielhafen eingeben (z. B. New York)", key="dest")
with col2:
    vessel_type = st.selectbox("Schiffstyp", list(VESSEL_TYPES.keys()))
    start_date = st.date_input("Startdatum", datetime.utcnow().date())

# Risikoanalyse starten
if st.button("Risikoanalyse starten"):
    if not origin_city or not dest_city:
        st.error("Bitte geben Sie Start- und Zielhafen ein.")
    elif origin_city.lower() == dest_city.lower():
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        with st.spinner("Lade Daten..."):
            # Geocoding
            origin_coords = geocode_city(origin_city)
            dest_coords = geocode_city(dest_city)

            if origin_coords and dest_coords:
                origin_lat, origin_lon = origin_coords
                dest_lat, dest_lon = dest_coords

                st.success(f"{origin_city} → {dest_city}")
                st.write(f"Start-Koordinaten: ({origin_lat:.4f}, {origin_lon:.4f})")
                st.write(f"Ziel-Koordinaten: ({dest_lat:.4f}, {dest_lon:.4f})")

                # Wetterdaten abrufen
                forecast = fetch_open_meteo_forecast(
                    origin_lat, origin_lon, datetime.combine(start_date, datetime.min.time())
                )
                if not forecast:
                    st.error("❌ Wetterdaten konnten nicht geladen werden.")
                else:
                    # Risikoberechnung
                    ship_factor = VESSEL_TYPES[vessel_type]
                    risk_data = []
                    for entry in forecast[::24]:  # Täglich
                        risk = compute_risk(entry["wave_height"], entry["wind_speed"], ship_factor)
                        risk_data.append({
                            "Datum": entry["time"].strftime("%Y-%m-%d"),
                            "Wellenhöhe (m)": round(entry["wave_height"], 2),
                            "Windgeschw. (m/s)": round(entry["wind_speed"], 2),
                            "Risiko (0-100)": risk
                        })

                    # Daten anzeigen
                    df = pd.DataFrame(risk_data)
                    st.subheader("📊 Prognose & Risikoanalyse (7 Tage)")
                    st.dataframe(df, use_container_width=True)

                    # Interaktive Visualisierung mit Plotly
                    fig = px.line(
                        df,
                        x="Datum",
                        y=["Wellenhöhe (m)", "Windgeschw. (m/s)", "Risiko (0-100)"],
                        title="Wetter- und Risikoprognose",
                        labels={"value": "Wert", "variable": "Metrik"}
                    )
                    fig.update_layout(
                        xaxis_title="Datum",
                        yaxis_title="Wert",
                        legend_title="Metrik",
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig, use_container_width=True)
