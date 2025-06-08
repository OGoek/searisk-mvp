import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

# === SETTINGS ===
st.set_page_config(page_title="SeaRisk AI", page_icon="🚢")

st.title("🌊 SeaRisk AI – Maritime Risikobewertung mit Echtzeit-Wetterdaten")

# === INPUT FORM ===
with st.form("input_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Start-Hafen", "Rotterdam")
    with col2:
        destination = st.text_input("Ziel-Hafen", "New York")
    
    col3, col4 = st.columns(2)
    with col3:
        vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Tanker", "Fähre", "Fischkutter"])
    with col4:
        start_date = st.date_input("Startdatum", datetime.today())
    
    submitted = st.form_submit_button("Risiko berechnen")

# === DUMMY-COORDINATES FÜR HÄFEN ===
port_coords = {
    "Rotterdam": [51.9225, 4.47917],
    "New York": [40.7128, -74.0060]
}

# === API-KEYS ===
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006-52eefa98-4468-11f0-b16b-0242ac130006"
noaa_token = "QWTcLJKbRevQchwfIcdKlAdpSJAbxTgg"
metno_headers = {"User-Agent": "SeaRiskAI/you@example.com"}

# NOAA Funktion mit Fehlerbehandlung
def get_noaa_station(lat, lon):
    url = f"https://www.ncei.noaa.gov/cdo-web/api/v2/stations?extent={lat-0.1},{lon-0.1},{lat+0.1},{lon+0.1}"
    headers = {"token": noaa_token}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        stations = response.json().get("results", [])
        return stations[0]["name"] if stations else "Keine Station gefunden"
    except Exception as e:
        st.warning(f"⚠️ NOAA Fehler: {e}")
        return "Fehler bei NOAA"
from datetime import datetime, timedelta

def get_stormglass_forecast(lat, lon):
    end = datetime.utcnow() + timedelta(days=7)
    start = datetime.utcnow()
    url = f"https://api.stormglass.io/v2/weather/point"
    params = {
        'lat': lat,
        'lng': lon,
        'params': 'waveHeight,windSpeed',
        'start': int(start.timestamp()),
        'end': int(end.timestamp())
    }
    headers = {'Authorization': stormglass_api_key}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        forecast = []
        for hour in data.get("hours", [])[:7*24:24]:
            wave = hour.get("waveHeight", {}).get("noaa", 0)
            wind = hour.get("windSpeed", {}).get("noaa", 0)
            time = hour.get("time", "n/a")
            forecast.append({"time": time, "wave": wave, "wind": wind})
        return forecast
    except Exception as e:
        st.warning(f"⚠️ Stormglass Fehler: {e}")
        return []

def get_metno_forecast(lat, lon):
    url = f"https://api.met.no/weatherapi/oceanforecast/2.0/complete?lat={lat}&lon={lon}"
    try:
        response = requests.get(url, headers=metno_headers)
        response.raise_for_status()
        timeseries = response.json().get("properties", {}).get("timeseries", [])
        forecast = []
        for t in timeseries[:7*24:24]:
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
        st.warning(f"⚠️ Met.no Fehler: {e}")
        return []

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
if submitted:
    if origin not in port_coords or destination not in port_coords:
        st.error("Bitte gültige Häfen eingeben.")
    else:
        origin_lat, origin_lon = port_coords[origin]
        dest_lat, dest_lon = port_coords[destination]

        st.subheader("📍 Hafenpositionen")
        st.write(f"**{origin}** → ({origin_lat}, {origin_lon})")
        st.write(f"**{destination}** → ({dest_lat}, {dest_lon})")

        # NOAA Station
        noaa_station = get_noaa_station(origin_lat, origin_lon)
        st.info(f"📡 Nächste NOAA-Station: {noaa_station}")

        # Wetterdaten abrufen
        sg_data = get_stormglass_forecast(origin_lat, origin_lon)
        met_data = get_metno_forecast(origin_lat, origin_lon)

        st.write("📡 Stormglass-Daten", sg_data)
        st.write("🌐 Met.no-Daten", met_data)

        # Kombiniere Daten und berechne Risiko
        combined = []
        length = min(len(sg_data), len(met_data))
        for i in range(length):
            avg_wave = (sg_data[i]["wave"] + met_data[i]["wave"]) / 2
            avg_wind = (sg_data[i]["wind"] + met_data[i]["wind"]) / 2
            risk = compute_risk(avg_wave, avg_wind, vessel_type)
            combined.append({
                "Datum": sg_data[i]["time"][:10],
                "Wellenhöhe (m)": round(avg_wave, 2),
                "Windgeschw. (m/s)": round(avg_wind, 2),
                "Risikowert": risk
            })

        df = pd.DataFrame(combined)
        st.subheader("📊 7-Tage Risikoanalyse")
        st.dataframe(df)

        # Wasserweg-Route simulieren mit Wegpunkten
        # Beispiel: Rotterdam → Ärmelkanal → Atlantik → New York
        route_coords = [
            [origin_lon, origin_lat],          # Rotterdam
            [1.8, 50.9],                      # Ärmelkanal (z.B. Dover)
            [-10.0, 45.0],                   # Mittlerer Atlantik
            [-74.0060, 40.7128]              # New York
        ]

        route_df = pd.DataFrame(route_coords, columns=['lon', 'lat'])

        layer = pdk.Layer(
            "PathLayer",
            data=[{"path": route_coords}],
            get_path="path",
            get_width=5,
            get_color=[0, 100, 255],
            width_min_pixels=3,
        )

        midpoint_lon = sum([pt[0] for pt in route_coords]) / len(route_coords)
        midpoint_lat = sum([pt[1] for pt in route_coords]) / len(route_coords)

        view_state = pdk.ViewState(
            longitude=midpoint_lon,
            latitude=midpoint_lat,
            zoom=3,
            pitch=0,
        )

        st.subheader("🗺️ Realistische Schifffahrtsroute")
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
