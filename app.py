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

# Risiko-Berechnung
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

    # Unterschiedliches Risiko für Containerschiffe vs Panamax etc.
    if vessel_type in ["Panamax", "Suezmax", "VLCC"]:
        risk += 5  # Beispiel, leicht höheres Risiko für große Schiffe
    elif vessel_type == "Containerschiff":
        risk += 10  # Containerschiffe evtl. etwas höheres Risiko durch Containerverlust

    return min(risk, 100)

def calculate_trend(values):
    x = np.arange(len(values))
    y = np.array(values)
    if len(x) < 2:
        return 0
    a, _ = np.polyfit(x, y, 1)
    return a

# Stormglass API
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

# Met.no API
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

# Open-Meteo API korrekt mit parametern
def fetch_open_meteo_forecast(lat, lon, start_date, days=7):
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
        resp = requests.get("https://marine-api.open-meteo.com/v1/marine", params=params)
        resp.raise_for_status()
        data = resp.json()
        result = []
        hours = data.get("hourly", {})
        times = hours.get("time", [])
        waves = hours.get("wave_height", [])
        winds = hours.get("wind_speed_10m", [])
        for i in range(len(times)):
            result.append({
                "time": times[i],
                "wave": waves[i],
                "wind": winds[i]
            })
        return result
    except Exception as e:
        st.warning(f"⚠️ Open-Meteo API Fehler: {e}")
        return []

# Geocoding via Nominatim (OpenStreetMap)
def geocode_place(place_name):
    try:
        resp = requests.get("https://nominatim.openstreetmap.org/search",
                            params={"q": place_name, "format": "json", "limit": 1},
                            headers={"User-Agent": "SeaRiskAIApp/1.0 (your_email@example.com)"})
        resp.raise_for_status()
        data = resp.json()
        if data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return lat, lon
        else:
            st.error(f"Kein Ergebnis für Ort: {place_name}")
            return None, None
    except Exception as e:
        st.error(f"Geocoding Fehler: {e}")
        return None, None

# Streamlit UI
st.title("🚢 SeaRisk AI MVP")

col1, col2 = st.columns(2)

with col1:
    origin = st.text_input("Start-Hafen (z.B. Rotterdam)")
    destination = st.text_input("Ziel-Hafen (z.B. New York)")
    vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Panamax", "Suezmax", "VLCC"])

with col2:
    start_date = st.date_input("Startdatum", datetime.utcnow().date())
    st.write("**Hinweis:** Prognose für 7 Tage ab Startdatum.")

if st.button("Risikoanalyse starten"):
    if not origin or not destination:
        st.error("Bitte Start- und Ziel-Hafen eingeben.")
    elif origin.lower() == destination.lower():
        st.error("Start- und Zielhafen müssen unterschiedlich sein.")
    else:
        origin_lat, origin_lon = geocode_place(origin)
        dest_lat, dest_lon = geocode_place(destination)

        if None in [origin_lat, origin_lon, dest_lat, dest_lon]:
            st.error("Geokoordinaten konnten nicht ermittelt werden.")
        else:
            st.subheader("📍 Hafenkoordinaten")
            st.write(f"{origin}: ({origin_lat:.4f}, {origin_lon:.4f})")
            st.write(f"{destination}: ({dest_lat:.4f}, {dest_lon:.4f})")

            # Historische Daten (30 Tage)
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

            # Prognose Daten (7 Tage ab Startdatum)
            start_forecast = datetime.combine(start_date, datetime.min.time())

            sg_forecast = get_stormglass_data(origin_lat, origin_lon, start_forecast, start_forecast + timedelta(days=7))
            met_forecast = get_metno_forecast(origin_lat, origin_lon)
            openmeteo_forecast = fetch_open_meteo_forecast(origin_lat, origin_lon, start_forecast, days=7)

            # Prüfen, welche Prognosen vorhanden sind, kombinieren wenn möglich
            forecasts = []
            if sg_forecast:
                forecasts.append(sg_forecast)
            if met_forecast:
                forecasts.append(met_forecast)
            if openmeteo_forecast:
                forecasts.append(openmeteo_forecast)

            if not forecasts:
                st.error("Keine Prognosedaten verfügbar.")
            else:
                # Mittelwerte aus allen verfügbaren Quellen berechnen
                min_len = min(len(f) for f in forecasts)
                combined = []
                for i in range(min_len):
                    avg_wave = np.mean([f[i]["wave"] for f in forecasts])
                    avg_wind = np.mean([f[i]["wind"] for f in forecasts])
                    risk = compute_risk(avg_wave, avg_wind, vessel_type)
                    combined.append({
                        "time": forecasts[0][i]["time"][:10],  # Datum aus erster Quelle
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

                # Diagramm
                fig, ax = plt.subplots(figsize=(10,4))
                ax.plot(df["time"], df["wave"], label="Wellenhöhe (m)")
                ax.plot(df["time"], df["wind"], label="Windgeschwindigkeit (m/s)")
                ax.plot(df["time"], df["risk"], label="Risiko")
                ax.legend()
                ax.set_xticks(range(len(df["time"])))
                ax.set_xticklabels(df["time"], rotation=45)
                st.pyplot(fig)

            # Karte mit Start- und Zielhafen
            st.subheader("🗺️ Route auf Karte")
            route_data = pd.DataFrame({
                "lat": [origin_lat, dest_lat],
                "lon": [origin_lon, dest_lon],
                "name": [origin, destination]
            })

            st.pydeck_chart(pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v9",
                initial_view_state=pdk.ViewState(
                    latitude=(origin_lat + dest_lat) / 2,
                    longitude=(origin_lon + dest_lon) / 2,
                    zoom=3
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=route_data,
                        get_position='[lon, lat]',
                        get_color='[200, 30, 0, 160]',
                        get_radius=10000,
                    ),
                    pdk.Layer(
                        "LineLayer",
                        data=[{
                            "sourcePosition": [origin_lon, origin_lat],
                            "targetPosition": [dest_lon, dest_lat]
                        }],
                        get_source_position="sourcePosition",
                        get_target_position="targetPosition",
                        get_color=[0, 128, 255],
                        get_width=4,
                    )
                ]
            ))
